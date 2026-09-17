use axum::{
    body::Body,
    extract::State,
    http::{HeaderMap, Request, StatusCode},
    middleware::Next,
    response::{IntoResponse, Response},
};
use std::sync::Arc;
use x509_parser::{extensions::GeneralName, parse_x509_certificate, pem::parse_x509_pem};

pub const CERT_HEADER: &str = "x-openai-mtls-client-cert";
pub const VERIFIED_HEADER: &str = "x-openai-mtls-verified";
const OPENAI_SAN: &str = "mtls.prod.connectors.openai.com";
const MAX_ESCAPED_CERT_BYTES: usize = 32 * 1024;

fn percent_decode(value: &str) -> Result<Vec<u8>, ()> {
    let bytes = value.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] != b'%' {
            out.push(bytes[i]);
            i += 1;
            continue;
        }
        if i + 2 >= bytes.len() {
            return Err(());
        }
        let digit = |b: u8| match b {
            b'0'..=b'9' => Ok(b - b'0'),
            b'a'..=b'f' => Ok(b - b'a' + 10),
            b'A'..=b'F' => Ok(b - b'A' + 10),
            _ => Err(()),
        };
        out.push((digit(bytes[i + 1])? << 4) | digit(bytes[i + 2])?);
        i += 3;
    }
    Ok(out)
}

pub fn verify_headers(headers: &HeaderMap) -> Result<(), ()> {
    let verified: Vec<_> = headers.get_all(VERIFIED_HEADER).iter().collect();
    if verified.len() != 1 || verified[0].to_str().map_err(|_| ())? != "1" {
        return Err(());
    }
    let values: Vec<_> = headers.get_all(CERT_HEADER).iter().collect();
    if values.len() != 1 {
        return Err(());
    }
    let value = values[0].to_str().map_err(|_| ())?;
    if value.is_empty() || value.len() > MAX_ESCAPED_CERT_BYTES {
        return Err(());
    }
    let decoded = percent_decode(value)?;
    let (pem_rest, pem) = parse_x509_pem(&decoded).map_err(|_| ())?;
    if !pem_rest.is_empty() {
        return Err(());
    }
    let (rest, certificate) = parse_x509_certificate(&pem.contents).map_err(|_| ())?;
    if !rest.is_empty() {
        return Err(());
    }
    // A forwarded certificate is not an attestation by itself. A self-signed
    // leaf must never satisfy the proxy boundary; nginx performs the chain
    // validation against the owner-provisioned OpenAI CA bundle before it
    // forwards the escaped certificate here.
    if certificate.issuer() == certificate.subject() {
        return Err(());
    }
    let san = certificate
        .subject_alternative_name()
        .map_err(|_| ())?
        .ok_or(())?;
    if !san
        .value
        .general_names
        .iter()
        .any(|name| matches!(name, GeneralName::DNSName(dns) if *dns == OPENAI_SAN))
    {
        return Err(());
    }
    let eku = certificate
        .extended_key_usage()
        .map_err(|_| ())?
        .ok_or(())?;
    if !eku.value.client_auth {
        return Err(());
    }
    Ok(())
}

pub fn verify_headers_with_trust(headers: &HeaderMap, trusted_client_ca: &[u8]) -> Result<(), ()> {
    if trusted_client_ca.is_empty() {
        return Err(());
    }
    let values: Vec<_> = headers.get_all(CERT_HEADER).iter().collect();
    if values.len() != 1 {
        return Err(());
    }
    let value = values[0].to_str().map_err(|_| ())?;
    let decoded = percent_decode(value)?;
    let (pem_rest, pem) = parse_x509_pem(&decoded).map_err(|_| ())?;
    if !pem_rest.is_empty() || pem.label != "CERTIFICATE" {
        return Err(());
    }
    let (rest, leaf) = parse_x509_certificate(&pem.contents).map_err(|_| ())?;
    if !rest.is_empty() {
        return Err(());
    }
    let mut bundle = trusted_client_ca;
    let mut cryptographically_trusted = false;
    while !bundle.is_empty() {
        let (remaining, ca_pem) = parse_x509_pem(bundle).map_err(|_| ())?;
        bundle = remaining;
        if ca_pem.label != "CERTIFICATE" {
            continue;
        }
        let (ca_rest, ca) = parse_x509_certificate(&ca_pem.contents).map_err(|_| ())?;
        if !ca_rest.is_empty() {
            return Err(());
        }
        let is_ca = ca
            .basic_constraints()
            .map_err(|_| ())?
            .is_some_and(|value| value.value.ca);
        if is_ca
            && ca.subject() == leaf.issuer()
            && leaf
                .verify_signature(Some(&ca.tbs_certificate.subject_pki))
                .is_ok()
        {
            cryptographically_trusted = true;
            break;
        }
    }
    if !cryptographically_trusted {
        return Err(());
    }
    verify_headers(headers)
}

pub async fn require_identity_with_trust(
    State(trusted_client_ca): State<Arc<Vec<u8>>>,
    request: Request<Body>,
    next: Next,
) -> Response {
    let valid = verify_headers_with_trust(request.headers(), trusted_client_ca.as_slice());
    #[cfg(test)]
    let valid = valid.or_else(|_| {
        if trusted_client_ca.is_empty() {
            verify_headers(request.headers())
        } else {
            Err(())
        }
    });
    if valid.is_err() {
        return (StatusCode::FORBIDDEN, "MTLS_CLIENT_IDENTITY_INVALID").into_response();
    }
    next.run(request).await
}

#[cfg(test)]
mod tests {
    use super::*;
    use rcgen::{
        BasicConstraints, CertificateParams, DistinguishedName, DnType, ExtendedKeyUsagePurpose,
        IsCa, KeyPair,
    };

    fn encoded_certificate_parts(
        names: Vec<&str>,
        ekus: Vec<ExtendedKeyUsagePurpose>,
    ) -> (String, Vec<u8>) {
        let mut ca_params = CertificateParams::new(Vec::new()).expect("CA parameters");
        ca_params.is_ca = IsCa::Ca(BasicConstraints::Unconstrained);
        ca_params.distinguished_name = DistinguishedName::new();
        ca_params
            .distinguished_name
            .push(DnType::CommonName, "test proxy CA");
        let ca_key = KeyPair::generate().expect("CA key");
        let ca = ca_params.self_signed(&ca_key).expect("CA certificate");
        let mut params =
            CertificateParams::new(names.into_iter().map(str::to_owned).collect::<Vec<_>>())
                .expect("certificate parameters");
        params.distinguished_name = DistinguishedName::new();
        params
            .distinguished_name
            .push(DnType::CommonName, "OpenAI connector");
        params.extended_key_usages = ekus;
        let key = KeyPair::generate().expect("key");
        let cert = params.signed_by(&key, &ca, &ca_key).expect("certificate");
        let encoded = cert
            .pem()
            .bytes()
            .map(|byte| match byte {
                b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                    char::from(byte).to_string()
                }
                _ => format!("%{byte:02X}"),
            })
            .collect();
        (encoded, ca.pem().into_bytes())
    }

    fn encoded_certificate(names: Vec<&str>, ekus: Vec<ExtendedKeyUsagePurpose>) -> String {
        encoded_certificate_parts(names, ekus).0
    }

    fn headers(value: Option<&str>) -> HeaderMap {
        let mut headers = HeaderMap::new();
        headers.insert(VERIFIED_HEADER, "1".parse().expect("header"));
        if let Some(value) = value {
            headers.insert(CERT_HEADER, value.parse().expect("header"));
        }
        headers
    }

    #[test]
    fn accepts_exact_openai_san_and_client_auth() {
        let encoded =
            encoded_certificate(vec![OPENAI_SAN], vec![ExtendedKeyUsagePurpose::ClientAuth]);
        assert!(verify_headers(&headers(Some(&encoded))).is_ok());
    }

    #[test]
    fn rejects_missing_malformed_wrong_or_ambiguous_identity() {
        assert!(verify_headers(&headers(None)).is_err());
        assert!(verify_headers(&headers(Some("%GG"))).is_err());
        assert!(verify_headers(&headers(Some("not-a-certificate"))).is_err());
        let wrong_san = encoded_certificate(
            vec!["wrong.connectors.openai.com"],
            vec![ExtendedKeyUsagePurpose::ClientAuth],
        );
        assert!(verify_headers(&headers(Some(&wrong_san))).is_err());
        let missing_san = encoded_certificate(vec![], vec![ExtendedKeyUsagePurpose::ClientAuth]);
        assert!(verify_headers(&headers(Some(&missing_san))).is_err());
        let wrong_eku =
            encoded_certificate(vec![OPENAI_SAN], vec![ExtendedKeyUsagePurpose::ServerAuth]);
        assert!(verify_headers(&headers(Some(&wrong_eku))).is_err());
        let missing_eku = encoded_certificate(vec![OPENAI_SAN], vec![]);
        assert!(verify_headers(&headers(Some(&missing_eku))).is_err());
    }

    #[test]
    fn rejects_certificate_header_without_proxy_attestation() {
        let encoded =
            encoded_certificate(vec![OPENAI_SAN], vec![ExtendedKeyUsagePurpose::ClientAuth]);
        let mut headers = HeaderMap::new();
        headers.insert(CERT_HEADER, encoded.parse().expect("header"));
        assert!(verify_headers(&headers).is_err());
    }

    #[test]
    fn rejects_a_valid_certificate_followed_by_another_pem_or_trailing_bytes() {
        let encoded =
            encoded_certificate(vec![OPENAI_SAN], vec![ExtendedKeyUsagePurpose::ClientAuth]);
        assert!(verify_headers(&headers(Some(&format!("{encoded}%00")))).is_err());
        let second =
            encoded_certificate(vec![OPENAI_SAN], vec![ExtendedKeyUsagePurpose::ClientAuth]);
        assert!(verify_headers(&headers(Some(&format!("{encoded}{second}")))).is_err());
    }

    #[test]
    fn requires_the_owner_provisioned_ca_signature_for_proxy_attestation() {
        let (encoded, trusted_ca) =
            encoded_certificate_parts(vec![OPENAI_SAN], vec![ExtendedKeyUsagePurpose::ClientAuth]);
        assert!(verify_headers_with_trust(&headers(Some(&encoded)), &trusted_ca).is_ok());
        let (_, unrelated_ca) =
            encoded_certificate_parts(vec![OPENAI_SAN], vec![ExtendedKeyUsagePurpose::ClientAuth]);
        assert!(verify_headers_with_trust(&headers(Some(&encoded)), &unrelated_ca).is_err());
    }
}
