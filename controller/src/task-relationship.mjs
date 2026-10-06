// Only the canonical same-repository Issue relationship is projected. Other
// repositories and unrelated PR prose retain their original content.
function relationshipPattern(repository) {
  const escaped = repository.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`\\b(close[sd]?|fix(?:es|ed)?|resolve[sd]?|Related to):?\\s+(#([1-9][0-9]*)|${escaped}#([1-9][0-9]*)|https://github\\.com/${escaped}/issues/([1-9][0-9]*))\\b`, 'gi');
}

export function taskReferences(body, repository) {
  return [...new Set([...String(body).matchAll(relationshipPattern(repository))]
    .map(match => Number(match[3] ?? match[4] ?? match[5])))];
}

export function nonClosingTaskBody(body, repository, task) {
  return String(body).replace(relationshipPattern(repository), (full, keyword, reference, short, qualified, url) =>
    Number(short ?? qualified ?? url) === task && keyword.toLowerCase() !== 'related to'
      ? `Related to #${task}` : full);
}
