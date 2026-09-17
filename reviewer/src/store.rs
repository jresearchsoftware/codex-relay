use rusqlite::{Connection, OptionalExtension};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Operation {
    pub status: String,
    pub review_id: Option<i64>,
    pub review_url: Option<String>,
    pub actor_login: Option<String>,
    pub check_id: Option<i64>,
    pub check_url: Option<String>,
}

pub struct Store {
    db: Connection,
}

impl Store {
    pub fn open(path: &str) -> rusqlite::Result<Self> {
        let db = Connection::open(path)?;
        db.execute_batch(
            "PRAGMA journal_mode=WAL;
             CREATE TABLE IF NOT EXISTS operations (
                 operation_id TEXT PRIMARY KEY, status TEXT NOT NULL,
                 review_id INTEGER, review_url TEXT, actor_login TEXT,
                 check_id INTEGER, check_url TEXT,
                 finding_digest TEXT NOT NULL DEFAULT '',
                 created_at INTEGER NOT NULL
             );
             CREATE TABLE IF NOT EXISTS events (
                 id INTEGER PRIMARY KEY, operation_id TEXT NOT NULL,
                 event_type TEXT NOT NULL, created_at INTEGER NOT NULL
             );",
        )?;
        // Existing relay databases predate Check Runs; SQLite has no ADD COLUMN IF NOT EXISTS.
        // Duplicate-column errors mean this database has already received the migration.
        let _ = db.execute("ALTER TABLE operations ADD COLUMN check_id INTEGER", []);
        let _ = db.execute("ALTER TABLE operations ADD COLUMN check_url TEXT", []);
        let _ = db.execute(
            "ALTER TABLE operations ADD COLUMN finding_digest TEXT NOT NULL DEFAULT ''",
            [],
        );
        Ok(Self { db })
    }

    pub fn reserve(&self, id: &str, finding_digest: &str) -> rusqlite::Result<bool> {
        let inserted = self.db.execute(
            "INSERT OR IGNORE INTO operations(operation_id,status,finding_digest,created_at)
             VALUES(?1,'RESERVED',?2,unixepoch())",
            (id, finding_digest),
        )? == 1;
        if inserted {
            self.event(id, "RESERVED")?;
            return Ok(true);
        }
        let retrying = self.db.execute(
            "UPDATE operations SET status='RESERVED' WHERE operation_id=?1 AND status='RETRYABLE_FAILURE'",
            [id],
        )? == 1;
        if retrying {
            self.event(id, "RETRYING")?;
        }
        Ok(retrying)
    }

    pub fn review_published(
        &self,
        id: &str,
        review_id: i64,
        url: &str,
        actor: &str,
    ) -> rusqlite::Result<()> {
        self.db.execute(
            "UPDATE operations SET status='REVIEW_PUBLISHED',review_id=?2,review_url=?3,actor_login=?4
             WHERE operation_id=?1",
            (id, review_id, url, actor),
        )?;
        self.event(id, "REVIEW_PUBLISHED")
    }

    pub fn published(&self, id: &str, check_id: i64, check_url: &str) -> rusqlite::Result<()> {
        self.db.execute(
            "UPDATE operations SET status='PUBLISHED',check_id=?2,check_url=?3 WHERE operation_id=?1",
            (id, check_id, check_url),
        )?;
        self.event(id, "PUBLISHED")
    }

    pub fn check_retryable_failure(&self, id: &str, outcome: &str) -> rusqlite::Result<()> {
        self.event(id, outcome)
    }

    pub fn retryable_failure(&self, id: &str) -> rusqlite::Result<()> {
        self.db.execute(
            "UPDATE operations SET status='RETRYABLE_FAILURE' WHERE operation_id=?1",
            [id],
        )?;
        self.event(id, "RETRYABLE_FAILURE")
    }

    pub fn known(&self, id: &str) -> rusqlite::Result<Option<Operation>> {
        self.db.query_row(
            "SELECT status,review_id,review_url,actor_login,check_id,check_url FROM operations WHERE operation_id=?1",
            [id],
            |r| Ok(Operation { status: r.get(0)?, review_id: r.get(1)?, review_url: r.get(2)?, actor_login: r.get(3)?, check_id: r.get(4)?, check_url: r.get(5)? }),
        ).optional()
    }

    fn event(&self, id: &str, event: &str) -> rusqlite::Result<()> {
        self.db.execute(
            "INSERT INTO events(operation_id,event_type,created_at) VALUES(?1,?2,unixepoch())",
            (id, event),
        )?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn reservation_and_publication_are_persisted() {
        let s = Store::open(":memory:").expect("store");
        assert!(s.reserve("a", "digest").expect("reserve"));
        assert!(!s.reserve("a", "digest").expect("duplicate"));
        s.review_published("a", 3, "https://example/3", "bot")
            .expect("record");
        s.published("a", 4, "https://example/check/4")
            .expect("check");
        assert_eq!(
            s.known("a").expect("known").expect("operation").status,
            "PUBLISHED"
        );
    }
    #[test]
    fn failed_operation_can_be_retried() {
        let s = Store::open(":memory:").expect("store");
        assert!(s.reserve("a", "digest").expect("reserve"));
        s.retryable_failure("a").expect("failure");
        assert!(s.reserve("a", "digest").expect("retry"));
    }
}
