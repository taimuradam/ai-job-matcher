from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from app.copilot.schemas import (
    ActionPlanData,
    CandidateProfileData,
    CandidateProfileRecord,
    FeedbackEventData,
    FeedbackLabel,
    FitAssessmentData,
    ImportBatchRecord,
    ImportFormat,
    LLMStatus,
    OpportunityData,
    OpportunityResult,
    ProviderFetchStatus,
    RawListingData,
    SearchRunDetailResponse,
    SearchRunDiagnostics,
    SearchRunRecord,
    SearchTargetData,
    SearchTargetRecord,
    WorkspaceSnapshotResponse,
)

DEFAULT_PROFILE_ID = "candidate_profile"
DEFAULT_TARGET_ID = "primary_search_target"


class SQLiteStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS profiles (
                    id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    profile_json TEXT NOT NULL,
                    llm_status_json TEXT NOT NULL,
                    PRIMARY KEY (id, version)
                );

                CREATE TABLE IF NOT EXISTS targets (
                    id TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    profile_version INTEGER NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    target_json TEXT NOT NULL,
                    PRIMARY KEY (id, version)
                );

                CREATE TABLE IF NOT EXISTS imports (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    format TEXT NOT NULL,
                    item_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    content TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS raw_listings (
                    id TEXT PRIMARY KEY,
                    run_id TEXT,
                    import_batch_id TEXT,
                    provider TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    external_id TEXT,
                    created_at TEXT NOT NULL,
                    listing_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS search_runs (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL,
                    profile_version INTEGER NOT NULL,
                    target_id TEXT NOT NULL,
                    target_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    diagnostics_json TEXT NOT NULL,
                    provider_statuses_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS opportunities (
                    row_id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    raw_listing_id TEXT,
                    dedupe_key TEXT NOT NULL,
                    opportunity_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS fit_assessments (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    opportunity_id TEXT NOT NULL,
                    assessment_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS feedback_events (
                    id TEXT PRIMARY KEY,
                    run_id TEXT,
                    opportunity_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    feedback_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS action_plans (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    opportunity_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    plan_json TEXT NOT NULL
                );
                """
            )
            self._migrate_opportunities_table(connection)
            connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_raw_listings_run_id ON raw_listings(run_id);
                CREATE INDEX IF NOT EXISTS idx_raw_listings_import_batch_id ON raw_listings(import_batch_id);
                CREATE INDEX IF NOT EXISTS idx_opportunities_run_id ON opportunities(run_id);
                CREATE INDEX IF NOT EXISTS idx_opportunities_opportunity_id ON opportunities(opportunity_id);
                CREATE INDEX IF NOT EXISTS idx_fit_assessments_run_id ON fit_assessments(run_id);
                CREATE INDEX IF NOT EXISTS idx_feedback_events_opportunity_id ON feedback_events(opportunity_id);
                CREATE INDEX IF NOT EXISTS idx_action_plans_run_opportunity ON action_plans(run_id, opportunity_id);
                """
            )

    def _table_columns(self, connection: sqlite3.Connection, table_name: str) -> set[str]:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {row["name"] for row in rows}

    def _migrate_opportunities_table(self, connection: sqlite3.Connection) -> None:
        columns = self._table_columns(connection, "opportunities")
        if not columns or {"row_id", "opportunity_id"}.issubset(columns):
            return

        if columns == {"id", "run_id", "raw_listing_id", "dedupe_key", "opportunity_json"}:
            connection.executescript(
                """
                ALTER TABLE opportunities RENAME TO opportunities_legacy;

                CREATE TABLE opportunities (
                    row_id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    raw_listing_id TEXT,
                    dedupe_key TEXT NOT NULL,
                    opportunity_json TEXT NOT NULL
                );

                INSERT INTO opportunities (row_id, opportunity_id, run_id, raw_listing_id, dedupe_key, opportunity_json)
                SELECT
                    id,
                    COALESCE(json_extract(opportunity_json, '$.id'), id),
                    run_id,
                    raw_listing_id,
                    dedupe_key,
                    opportunity_json
                FROM opportunities_legacy;

                DROP TABLE opportunities_legacy;
                """
            )
            return

        raise sqlite3.OperationalError(
            "Unsupported opportunities table schema. Delete app/data/copilot.sqlite3 to recreate it."
        )

    def reset(self) -> None:
        if self.db_path.exists():
            self.db_path.unlink()
        self.initialize()

    def _next_version(self, table: str, record_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT COALESCE(MAX(version), 0) AS version FROM {table} WHERE id = ?",
                (record_id,),
            ).fetchone()
        return int(row["version"]) + 1

    def save_profile(
        self,
        *,
        profile: CandidateProfileData,
        llm_status: LLMStatus | None = None,
    ) -> CandidateProfileRecord:
        created_at = datetime.now(UTC)
        version = self._next_version("profiles", DEFAULT_PROFILE_ID)
        llm_status = llm_status or LLMStatus()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO profiles (id, version, created_at, profile_json, llm_status_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    DEFAULT_PROFILE_ID,
                    version,
                    created_at.isoformat(),
                    profile.model_dump_json(),
                    llm_status.model_dump_json(),
                ),
            )
        return CandidateProfileRecord(
            id=DEFAULT_PROFILE_ID,
            version=version,
            created_at=created_at,
            profile=profile,
            llm_status=llm_status,
        )

    def save_target(
        self,
        *,
        profile_record: CandidateProfileRecord,
        target: SearchTargetData,
    ) -> SearchTargetRecord:
        created_at = datetime.now(UTC)
        version = self._next_version("targets", DEFAULT_TARGET_ID)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO targets (id, profile_id, profile_version, version, created_at, target_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    DEFAULT_TARGET_ID,
                    profile_record.id,
                    profile_record.version,
                    version,
                    created_at.isoformat(),
                    target.model_dump_json(),
                ),
            )
        return SearchTargetRecord(
            id=DEFAULT_TARGET_ID,
            profile_id=profile_record.id,
            profile_version=profile_record.version,
            version=version,
            created_at=created_at,
            target=target,
        )

    def latest_profile(self) -> CandidateProfileRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM profiles
                WHERE id = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (DEFAULT_PROFILE_ID,),
            ).fetchone()
        if row is None:
            return None
        return CandidateProfileRecord(
            id=row["id"],
            version=row["version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            profile=CandidateProfileData.model_validate_json(row["profile_json"]),
            llm_status=LLMStatus.model_validate_json(row["llm_status_json"]),
        )

    def latest_target(self) -> SearchTargetRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM targets
                WHERE id = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (DEFAULT_TARGET_ID,),
            ).fetchone()
        if row is None:
            return None
        return SearchTargetRecord(
            id=row["id"],
            profile_id=row["profile_id"],
            profile_version=row["profile_version"],
            version=row["version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            target=SearchTargetData.model_validate_json(row["target_json"]),
        )

    def profile_snapshot(self, record_id: str, version: int) -> CandidateProfileRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM profiles WHERE id = ? AND version = ?",
                (record_id, version),
            ).fetchone()
        if row is None:
            raise KeyError("Profile snapshot not found.")
        return CandidateProfileRecord(
            id=row["id"],
            version=row["version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            profile=CandidateProfileData.model_validate_json(row["profile_json"]),
            llm_status=LLMStatus.model_validate_json(row["llm_status_json"]),
        )

    def target_snapshot(self, record_id: str, version: int) -> SearchTargetRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM targets WHERE id = ? AND version = ?",
                (record_id, version),
            ).fetchone()
        if row is None:
            raise KeyError("Target snapshot not found.")
        return SearchTargetRecord(
            id=row["id"],
            profile_id=row["profile_id"],
            profile_version=row["profile_version"],
            version=row["version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            target=SearchTargetData.model_validate_json(row["target_json"]),
        )

    def save_import_batch(
        self,
        *,
        format_name: ImportFormat,
        label: str,
        content: str,
        listings: list[RawListingData],
    ) -> ImportBatchRecord:
        created_at = datetime.now(UTC)
        batch_id = str(uuid4())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO imports (id, label, format, item_count, created_at, content)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (batch_id, label, format_name, len(listings), created_at.isoformat(), content),
            )
            for listing in listings:
                connection.execute(
                    """
                    INSERT INTO raw_listings (id, run_id, import_batch_id, provider, source_type, external_id, created_at, listing_json)
                    VALUES (?, NULL, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
                        batch_id,
                        listing.source,
                        listing.source_type,
                        listing.external_id,
                        created_at.isoformat(),
                        listing.model_dump_json(),
                    ),
                )
        return ImportBatchRecord(
            id=batch_id,
            label=label,
            format=format_name,
            item_count=len(listings),
            created_at=created_at,
        )

    def list_import_batches(self) -> list[ImportBatchRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM imports ORDER BY created_at DESC"
            ).fetchall()
        return [
            ImportBatchRecord(
                id=row["id"],
                label=row["label"],
                format=row["format"],
                item_count=row["item_count"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def list_imported_raw_listings(self) -> list[tuple[str, RawListingData]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, listing_json
                FROM raw_listings
                WHERE import_batch_id IS NOT NULL
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [
            (row["id"], RawListingData.model_validate_json(row["listing_json"]))
            for row in rows
        ]

    def create_search_run(
        self,
        *,
        profile_record: CandidateProfileRecord,
        target_record: SearchTargetRecord,
    ) -> SearchRunRecord:
        return SearchRunRecord(
            id=str(uuid4()),
            profile_id=profile_record.id,
            profile_version=profile_record.version,
            target_id=target_record.id,
            target_version=target_record.version,
            created_at=datetime.now(UTC),
        )

    def save_run_raw_listings(
        self,
        *,
        run_id: str,
        listings: list[RawListingData],
    ) -> list[tuple[str, RawListingData]]:
        created_at = datetime.now(UTC).isoformat()
        persisted: list[tuple[str, RawListingData]] = []
        with self._connect() as connection:
            for listing in listings:
                listing_id = str(uuid4())
                connection.execute(
                    """
                    INSERT INTO raw_listings (id, run_id, import_batch_id, provider, source_type, external_id, created_at, listing_json)
                    VALUES (?, ?, NULL, ?, ?, ?, ?, ?)
                    """,
                    (
                        listing_id,
                        run_id,
                        listing.source,
                        listing.source_type,
                        listing.external_id,
                        created_at,
                        listing.model_dump_json(),
                    ),
                )
                persisted.append((listing_id, listing))
        return persisted

    def finalize_search_run(
        self,
        *,
        run: SearchRunRecord,
        diagnostics: SearchRunDiagnostics,
        provider_statuses: list[ProviderFetchStatus],
        opportunities: list[OpportunityData],
        assessments: dict[str, FitAssessmentData],
        action_plans: dict[str, ActionPlanData],
    ) -> SearchRunRecord:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO search_runs (id, profile_id, profile_version, target_id, target_version, created_at, diagnostics_json, provider_statuses_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.profile_id,
                    run.profile_version,
                    run.target_id,
                    run.target_version,
                    run.created_at.isoformat(),
                    diagnostics.model_dump_json(),
                    json.dumps([status.model_dump(mode="json") for status in provider_statuses]),
                ),
            )
            for opportunity in opportunities:
                connection.execute(
                    """
                    INSERT INTO opportunities (row_id, opportunity_id, run_id, raw_listing_id, dedupe_key, opportunity_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
                        opportunity.id,
                        run.id,
                        opportunity.raw_listing_id,
                        opportunity.dedupe_key,
                        opportunity.model_dump_json(),
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO fit_assessments (id, run_id, opportunity_id, assessment_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
                        run.id,
                        opportunity.id,
                        assessments[opportunity.id].model_dump_json(),
                    ),
                )
                if opportunity.id in action_plans:
                    connection.execute(
                        """
                        INSERT INTO action_plans (id, run_id, opportunity_id, created_at, updated_at, plan_json)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(uuid4()),
                            run.id,
                            opportunity.id,
                            run.created_at.isoformat(),
                            datetime.now(UTC).isoformat(),
                            action_plans[opportunity.id].model_dump_json(),
                        ),
                    )
        run.diagnostics = diagnostics
        run.provider_statuses = provider_statuses
        return run

    def latest_run_id(self) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM search_runs ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return row["id"] if row else None

    def search_run(self, run_id: str) -> SearchRunDetailResponse:
        with self._connect() as connection:
            run_row = connection.execute(
                "SELECT * FROM search_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if run_row is None:
                raise KeyError("Search run not found.")
            opportunity_rows = connection.execute(
                "SELECT * FROM opportunities WHERE run_id = ?",
                (run_id,),
            ).fetchall()
            assessment_rows = connection.execute(
                "SELECT opportunity_id, assessment_json FROM fit_assessments WHERE run_id = ?",
                (run_id,),
            ).fetchall()
            feedback_rows = connection.execute(
                "SELECT opportunity_id, feedback_json FROM feedback_events WHERE run_id = ? ORDER BY created_at DESC",
                (run_id,),
            ).fetchall()
            plan_rows = connection.execute(
                "SELECT opportunity_id, plan_json FROM action_plans WHERE run_id = ?",
                (run_id,),
            ).fetchall()

        run = SearchRunRecord(
            id=run_row["id"],
            profile_id=run_row["profile_id"],
            profile_version=run_row["profile_version"],
            target_id=run_row["target_id"],
            target_version=run_row["target_version"],
            created_at=datetime.fromisoformat(run_row["created_at"]),
            diagnostics=SearchRunDiagnostics.model_validate_json(run_row["diagnostics_json"]),
            provider_statuses=[
                ProviderFetchStatus.model_validate(item)
                for item in json.loads(run_row["provider_statuses_json"])
            ],
        )
        profile = self.profile_snapshot(run.profile_id, run.profile_version)
        target = self.target_snapshot(run.target_id, run.target_version)
        assessments = {
            row["opportunity_id"]: FitAssessmentData.model_validate_json(row["assessment_json"])
            for row in assessment_rows
        }
        plans = {
            row["opportunity_id"]: ActionPlanData.model_validate_json(row["plan_json"])
            for row in plan_rows
        }
        feedback_map: dict[str, list[FeedbackEventData]] = {}
        for row in feedback_rows:
                feedback_map.setdefault(row["opportunity_id"], []).append(
                    FeedbackEventData.model_validate_json(row["feedback_json"])
                )
        results = [
            OpportunityResult(
                opportunity=OpportunityData.model_validate_json(row["opportunity_json"]),
                assessment=assessments[row["opportunity_id"]],
                action_plan=plans.get(row["opportunity_id"]),
                feedback=feedback_map.get(row["opportunity_id"], []),
            )
            for row in opportunity_rows
        ]
        results.sort(
            key=lambda item: (
                item.assessment.triage_decision != "apply",
                item.assessment.triage_decision != "tailor",
                -item.assessment.scores.total,
            )
        )
        return SearchRunDetailResponse(
            run=run,
            profile=profile,
            target=target,
            results=results,
        )

    def feedback_events(
        self,
        *,
        run_id: str | None = None,
        opportunity_id: str | None = None,
    ) -> list[FeedbackEventData]:
        clauses: list[str] = []
        params: list[str] = []
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        if opportunity_id:
            clauses.append("opportunity_id = ?")
            params.append(opportunity_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT feedback_json FROM feedback_events {where} ORDER BY created_at DESC",
                params,
            ).fetchall()
        return [FeedbackEventData.model_validate_json(row["feedback_json"]) for row in rows]

    def save_feedback(
        self,
        *,
        opportunity_id: str,
        label: FeedbackLabel,
        note: str | None = None,
        run_id: str | None = None,
    ) -> FeedbackEventData | None:
        run_scope = run_id
        if run_scope is None:
            run_scope = self.latest_run_id()
        with self._connect() as connection:
            opportunity_row = connection.execute(
                """
                SELECT opportunity_json FROM opportunities
                WHERE opportunity_id = ? AND (? IS NULL OR run_id = ?)
                LIMIT 1
                """,
                (opportunity_id, run_scope, run_scope),
            ).fetchone()
            if opportunity_row is None:
                return None
            opportunity = OpportunityData.model_validate_json(opportunity_row["opportunity_json"])
            event = FeedbackEventData(
                label=label,
                note=note,
                created_at=datetime.now(UTC),
                normalized_title=opportunity.normalized_title,
                required_skills=opportunity.required_skills,
                location_type=opportunity.location_type,
            )
            connection.execute(
                """
                INSERT INTO feedback_events (id, run_id, opportunity_id, created_at, feedback_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    run_scope,
                    opportunity_id,
                    event.created_at.isoformat(),
                    event.model_dump_json(),
                ),
            )
        return event

    def action_plan(self, *, run_id: str, opportunity_id: str) -> ActionPlanData | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT plan_json
                FROM action_plans
                WHERE run_id = ? AND opportunity_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (run_id, opportunity_id),
            ).fetchone()
        if row is None:
            return None
        return ActionPlanData.model_validate_json(row["plan_json"])

    def save_action_plan(
        self,
        *,
        run_id: str,
        opportunity_id: str,
        plan: ActionPlanData,
    ) -> ActionPlanData:
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO action_plans (id, run_id, opportunity_id, created_at, updated_at, plan_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    run_id,
                    opportunity_id,
                    now,
                    now,
                    plan.model_dump_json(),
                ),
            )
        return plan

    def workspace_snapshot(self) -> WorkspaceSnapshotResponse:
        profile = self.latest_profile()
        target = self.latest_target()
        latest_run_id = self.latest_run_id()
        latest_run = self.search_run(latest_run_id) if latest_run_id else None
        return WorkspaceSnapshotResponse(
            profile=profile,
            target=target,
            imports=self.list_import_batches(),
            latest_run=latest_run,
        )

    def reset_workspace(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                DELETE FROM action_plans;
                DELETE FROM feedback_events;
                DELETE FROM fit_assessments;
                DELETE FROM opportunities;
                DELETE FROM search_runs;
                DELETE FROM raw_listings;
                DELETE FROM imports;
                DELETE FROM targets;
                DELETE FROM profiles;
                """
            )
