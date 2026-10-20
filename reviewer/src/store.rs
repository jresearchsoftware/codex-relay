use rusqlite::{Connection, OptionalExtension, TransactionBehavior};
use std::time::Duration;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Operation {
    pub status: String,
}

/// A possible Check Run send and the prior value for a proven no-effect rollback.
#[derive(Debug, PartialEq, Eq)]
pub struct CheckSendReservation {
    pub previous: Option<i64>,
    pub next: i64,
}

pub struct Store {
    db: Connection,
    insert_publication_sql: String,
}

impl Store {
    pub fn open(path: &str) -> rusqlite::Result<Self> {
        let mut db = Connection::open(path)?;
        db.busy_timeout(Duration::from_secs(5))?;
        db.execute_batch("PRAGMA journal_mode=WAL;")?;
        // Serialize only the short schema change. Historical receipt columns
        // and event history remain untouched compatibility data.
        let transaction = db.transaction_with_behavior(TransactionBehavior::Immediate)?;
        transaction.execute_batch(
            "CREATE TABLE IF NOT EXISTS operations (
                 operation_id TEXT PRIMARY KEY, status TEXT NOT NULL,
                 publication_body TEXT, authority_binding TEXT,
                 step_binding TEXT, check_intent INTEGER
             );",
        )?;
        let columns = {
            let mut statement = transaction.prepare("PRAGMA table_info(operations)")?;
            let rows = statement.query_map([], |row| row.get::<_, String>(1))?;
            rows.collect::<rusqlite::Result<Vec<_>>>()?
        };
        for (name, definition) in [
            ("publication_body", "publication_body TEXT"),
            ("authority_binding", "authority_binding TEXT"),
            ("step_binding", "step_binding TEXT"),
            ("check_intent", "check_intent INTEGER"),
        ] {
            if !columns.iter().any(|column| column == name) {
                transaction.execute(
                    &format!("ALTER TABLE operations ADD COLUMN {definition}"),
                    [],
                )?;
            }
        }
        // Old schemas require these columns without SQL defaults. Supply inert
        // compatibility values, not new publication diagnostics or authority.
        let mut legacy_columns = String::new();
        let mut legacy_values = String::new();
        if columns.iter().any(|column| column == "finding_digest") {
            legacy_columns.push_str(",finding_digest");
            legacy_values.push_str(",''");
        }
        if columns.iter().any(|column| column == "created_at") {
            legacy_columns.push_str(",created_at");
            legacy_values.push_str(",0");
        }
        let insert_publication_sql = format!(
            "INSERT OR IGNORE INTO operations(operation_id,status,publication_body,check_intent{legacy_columns})
             VALUES(?1,'RESERVED',?2,?3{legacy_values})"
        );
        transaction.commit()?;
        Ok(Self {
            db,
            insert_publication_sql,
        })
    }

    /// Freeze renderer bytes atomically with the decisive-publication intent.
    /// Pre-upgrade rows without frozen bytes retain their legacy renderer.
    pub fn reserve_publication(
        &self,
        id: &str,
        current_body: &str,
        legacy_body: &str,
    ) -> rusqlite::Result<(bool, String)> {
        self.reserve_with_check_intent(id, current_body, legacy_body, Some(0))
    }

    /// An observed native publication with no local row may already have sent
    /// a Check. Retain unknown history and grant only one prospective recovery.
    pub fn recover_publication(
        &self,
        id: &str,
        body: &str,
        legacy_body: &str,
    ) -> rusqlite::Result<(bool, String)> {
        self.reserve_with_check_intent(id, body, legacy_body, None)
    }

    fn reserve_with_check_intent(
        &self,
        id: &str,
        current_body: &str,
        legacy_body: &str,
        check_intent: Option<i64>,
    ) -> rusqlite::Result<(bool, String)> {
        let transaction = self.db.unchecked_transaction()?;
        let inserted = transaction.execute(
            &self.insert_publication_sql,
            (id, current_body, check_intent),
        )? == 1;
        transaction.execute(
            "UPDATE operations SET publication_body=?2 WHERE operation_id=?1 AND publication_body IS NULL",
            (id, legacy_body),
        )?;
        let retrying = !inserted && transaction.execute(
            "UPDATE operations SET status='RESERVED' WHERE operation_id=?1 AND status='RETRYABLE_FAILURE'",
            [id],
        )? == 1;
        let body = transaction.query_row(
            "SELECT publication_body FROM operations WHERE operation_id=?1",
            [id],
            |row| row.get(0),
        )?;
        transaction.commit()?;
        Ok((inserted || retrying, body))
    }

    /// Re-arm only a publication proven not to have taken effect. Historical
    /// completed states never become fresh decisive-publication permission.
    pub fn retryable_failure(&self, id: &str) -> rusqlite::Result<()> {
        self.db.execute(
            "UPDATE operations SET status='RETRYABLE_FAILURE' WHERE operation_id=?1 AND status='RESERVED'",
            [id],
        )?;
        Ok(())
    }

    pub fn known(&self, id: &str) -> rusqlite::Result<Option<Operation>> {
        self.db
            .query_row(
                "SELECT status FROM operations WHERE operation_id=?1",
                [id],
                |row| {
                    Ok(Operation {
                        status: row.get(0)?,
                    })
                },
            )
            .optional()
    }

    pub fn authority_binding(&self, id: &str) -> rusqlite::Result<Option<String>> {
        self.db
            .query_row(
                "SELECT authority_binding FROM operations WHERE operation_id=?1",
                [id],
                |row| row.get(0),
            )
            .optional()
            .map(Option::flatten)
    }

    pub fn bind_authority(&self, id: &str, binding: &str) -> rusqlite::Result<()> {
        self.db.execute(
            "UPDATE operations SET authority_binding=?2 WHERE operation_id=?1 AND authority_binding IS NULL",
            (id, binding),
        )?;
        Ok(())
    }

    /// One original possible Check Run send and one bounded recovery send.
    /// An unknown historical intent receives only a prospective recovery send;
    /// this never invents an original observation for a pre-upgrade row.
    pub fn reserve_check_send(&self, id: &str) -> rusqlite::Result<Option<CheckSendReservation>> {
        let transaction =
            rusqlite::Transaction::new_unchecked(&self.db, TransactionBehavior::Immediate)?;
        let previous: Option<Option<i64>> = self
            .db
            .query_row(
                "SELECT check_intent FROM operations WHERE operation_id=?1",
                [id],
                |row| row.get(0),
            )
            .optional()?;
        let Some(previous) = previous else {
            return Ok(None);
        };
        let next = match previous {
            Some(0) => 1,
            Some(1) | None => 2,
            _ => return Ok(None),
        };
        let reserved = transaction.execute(
            "UPDATE operations SET check_intent=?3 WHERE operation_id=?1 AND check_intent IS ?2",
            (id, previous, next),
        )? == 1;
        transaction.commit()?;
        Ok(reserved.then_some(CheckSendReservation { previous, next }))
    }

    pub fn restore_check_send(
        &self,
        id: &str,
        reservation: CheckSendReservation,
    ) -> rusqlite::Result<bool> {
        if !matches!(
            (reservation.previous, reservation.next),
            (Some(0), 1) | (Some(1), 2) | (None, 2)
        ) {
            return Ok(false);
        }
        // A concurrent sender may already have spent the second grant. Refund
        // exactly this single-use no-effect send, retaining every other possible
        // effect. Restoring the old value would erase another sender or strand
        // this rejection. NULL history has no concurrent grant available.
        Ok(if reservation.previous.is_none() {
            self.db.execute(
                "UPDATE operations SET check_intent=NULL WHERE operation_id=?1 AND check_intent=2",
                [id],
            )? == 1
        } else {
            self.db.execute("UPDATE operations SET check_intent=check_intent-1 WHERE operation_id=?1 AND check_intent IN (1,2)", [id])? == 1
        })
    }

    pub fn publication_body(&self, id: &str) -> rusqlite::Result<Option<String>> {
        self.db
            .query_row(
                "SELECT publication_body FROM operations WHERE operation_id=?1",
                [id],
                |row| row.get(0),
            )
            .optional()
            .map(Option::flatten)
    }

    pub fn step_binding(&self, id: &str) -> rusqlite::Result<Option<String>> {
        self.db
            .query_row(
                "SELECT step_binding FROM operations WHERE operation_id=?1",
                [id],
                |row| row.get(0),
            )
            .optional()
            .map(Option::flatten)
    }

    pub fn bind_step(&self, id: &str, binding: &str) -> rusqlite::Result<()> {
        self.db.execute(
            "UPDATE operations SET step_binding=?2 WHERE operation_id=?1 AND step_binding IS NULL",
            (id, binding),
        )?;
        Ok(())
    }

    pub fn upgrade_step_binding(
        &self,
        id: &str,
        previous: &str,
        binding: &str,
    ) -> rusqlite::Result<bool> {
        Ok(self.db.execute(
            "UPDATE operations SET step_binding=?3 WHERE operation_id=?1 AND step_binding=?2",
            (id, previous, binding),
        )? == 1)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Arc, Barrier};

    struct Database(std::path::PathBuf);
    impl Database {
        fn new() -> Self {
            static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
            Self(std::env::temp_dir().join(format!(
                    "relay-reviewer-store-{}-{}-{}.sqlite3",
                    std::process::id(),
                    std::time::SystemTime::now()
                        .duration_since(std::time::UNIX_EPOCH)
                        .unwrap()
                        .as_nanos(),
                    NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
                )))
        }
        fn path(&self) -> &str {
            self.0.to_str().unwrap()
        }
    }
    impl Drop for Database {
        fn drop(&mut self) {
            for suffix in ["", "-wal", "-shm"] {
                let _ = std::fs::remove_file(format!("{}{suffix}", self.path()));
            }
        }
    }

    #[test]
    fn fresh_schema_has_only_publication_intent_and_original_bindings() {
        let store = Store::open(":memory:").unwrap();
        let mut statement = store.db.prepare("PRAGMA table_info(operations)").unwrap();
        let columns = statement
            .query_map([], |row| row.get::<_, String>(1))
            .unwrap()
            .collect::<rusqlite::Result<Vec<_>>>()
            .unwrap();
        assert_eq!(
            columns,
            [
                "operation_id",
                "status",
                "publication_body",
                "authority_binding",
                "step_binding",
                "check_intent"
            ]
        );
        assert_eq!(
            store
                .db
                .query_row(
                    "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='events'",
                    [],
                    |row| row.get::<_, usize>(0)
                )
                .unwrap(),
            0
        );
    }

    #[test]
    fn original_body_and_bindings_survive_safe_retry_and_restart() {
        let database = Database::new();
        {
            let store = Store::open(database.path()).unwrap();
            assert_eq!(
                store
                    .reserve_publication("a", "original", "legacy")
                    .unwrap(),
                (true, "original".into())
            );
            store.bind_authority("a", "authority").unwrap();
            store.bind_step("a", "step").unwrap();
            store.retryable_failure("a").unwrap();
        }
        let store = Store::open(database.path()).unwrap();
        assert_eq!(
            store.reserve_publication("a", "changed", "legacy").unwrap(),
            (true, "original".into())
        );
        store.bind_authority("a", "changed").unwrap();
        store.bind_step("a", "changed").unwrap();
        assert_eq!(
            store.authority_binding("a").unwrap().as_deref(),
            Some("authority")
        );
        assert_eq!(store.step_binding("a").unwrap().as_deref(), Some("step"));
        assert!(
            !store
                .reserve_publication("a", "changed", "legacy")
                .unwrap()
                .0
        );
    }

    #[test]
    fn historical_rows_and_events_are_preserved_without_new_receipt_writes() {
        let database = Database::new();
        {
            let db = Connection::open(database.path()).unwrap();
            db.execute_batch(
                "CREATE TABLE operations(operation_id TEXT PRIMARY KEY,status TEXT NOT NULL,
                 review_id INTEGER,review_url TEXT,actor_login TEXT,check_id INTEGER,check_url TEXT,
                 finding_digest TEXT NOT NULL,created_at INTEGER NOT NULL);
                 CREATE TABLE events(id INTEGER PRIMARY KEY,operation_id TEXT NOT NULL,
                 event_type TEXT NOT NULL,created_at INTEGER NOT NULL);
                 INSERT INTO operations VALUES('old','PUBLISHED',7,'review','bot',8,'check','finding',9);
                 INSERT INTO events VALUES(1,'old','PUBLISHED',9);"
            ).unwrap();
        }
        let store = Store::open(database.path()).unwrap();
        assert_eq!(
            store
                .reserve_publication("old", "current", "legacy")
                .unwrap(),
            (false, "legacy".into())
        );
        store.retryable_failure("old").unwrap();
        assert_eq!(store.known("old").unwrap().unwrap().status, "PUBLISHED");
        assert_eq!(store.db.query_row(
            "SELECT review_id,check_id,finding_digest,created_at FROM operations WHERE operation_id='old'",
            [], |row| Ok((row.get::<_, i64>(0)?, row.get::<_, i64>(1)?,
                row.get::<_, String>(2)?, row.get::<_, i64>(3)?))).unwrap(),
            (7, 8, "finding".into(), 9));
        assert!(
            store
                .reserve_publication("new", "current", "legacy")
                .unwrap()
                .0
        );
        assert_eq!(
            store
                .db
                .query_row("SELECT count(*) FROM events", [], |row| row
                    .get::<_, usize>(0))
                .unwrap(),
            1
        );
        assert_eq!(
            store.reserve_check_send("old").unwrap(),
            Some(CheckSendReservation {
                previous: None,
                next: 2
            })
        );
        assert_eq!(store.reserve_check_send("old").unwrap(), None);
    }

    #[test]
    fn check_send_budget_is_durable_and_concurrent_rejections_refund_only_their_send() {
        let database = Database::new();
        let first = {
            let store = Store::open(database.path()).unwrap();
            store.reserve_publication("a", "body", "legacy").unwrap();
            store.reserve_check_send("a").unwrap().unwrap()
        };
        assert_eq!(
            first,
            CheckSendReservation {
                previous: Some(0),
                next: 1
            }
        );
        let store = Store::open(database.path()).unwrap();
        let recovery = store.reserve_check_send("a").unwrap().unwrap();
        assert_eq!(
            recovery,
            CheckSendReservation {
                previous: Some(1),
                next: 2
            }
        );
        assert!(store.restore_check_send("a", first).unwrap());
        let concurrent = store.reserve_check_send("a").unwrap().unwrap();
        assert_eq!(store.reserve_check_send("a").unwrap(), None);
        assert!(store.restore_check_send("a", recovery).unwrap());
        assert!(store.restore_check_send("a", concurrent).unwrap());
        assert_eq!(
            store.reserve_check_send("a").unwrap().unwrap().previous,
            Some(0)
        );
        assert_eq!(store.reserve_check_send("missing").unwrap(), None);
    }

    #[test]
    fn concurrent_process_connections_reserve_one_decisive_publication() {
        let database = Database::new();
        drop(Store::open(database.path()).unwrap());
        let barrier = Arc::new(Barrier::new(2));
        let handles: Vec<_> = ["first", "second"]
            .into_iter()
            .map(|body| {
                let path = database.path().to_owned();
                let barrier = barrier.clone();
                std::thread::spawn(move || {
                    let store = Store::open(&path).unwrap();
                    barrier.wait();
                    store.reserve_publication("same", body, "legacy").unwrap()
                })
            })
            .collect();
        let results: Vec<_> = handles
            .into_iter()
            .map(|handle| handle.join().unwrap())
            .collect();
        assert_eq!(results.iter().filter(|(reserved, _)| *reserved).count(), 1);
        assert_eq!(results[0].1, results[1].1);
        let store = Store::open(database.path()).unwrap();
        assert!(
            !store
                .reserve_publication("same", "later", "legacy")
                .unwrap()
                .0
        );
        assert!(
            store
                .reserve_publication("unrelated", "body", "legacy")
                .unwrap()
                .0
        );
    }
}
