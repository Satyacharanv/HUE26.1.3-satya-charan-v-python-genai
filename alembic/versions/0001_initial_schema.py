"""Initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-01-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role", sa.Enum("USER", "ADMIN", name="userrole"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.Enum("ZIP", "GITHUB", name="sourcetype"), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("CREATED", "PREPROCESSING", "ANALYZING", "PAUSED", "COMPLETED", "FAILED", name="projectstatus"),
            nullable=False,
        ),
        sa.Column("personas", sa.JSON(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
    )
    op.create_index(op.f("ix_projects_id"), "projects", ["id"], unique=False)

    op.create_table(
        "repository_metadata",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repository_type", sa.String(length=100), nullable=False),
        sa.Column("primary_framework", sa.String(length=100), nullable=True),
        sa.Column("secondary_frameworks", postgresql.JSONB(), nullable=True),
        sa.Column("total_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("code_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("test_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("config_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documentation_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("entry_points", postgresql.JSONB(), nullable=True),
        sa.Column("config_files_list", postgresql.JSONB(), nullable=True),
        sa.Column("dependencies", postgresql.JSONB(), nullable=True),
        sa.Column("is_preprocessed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("preprocessing_status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("preprocessing_error", sa.Text(), nullable=True),
        sa.Column("file_count_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_chunks_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.UniqueConstraint("project_id"),
    )
    op.create_index(op.f("ix_repository_metadata_id"), "repository_metadata", ["id"], unique=False)
    op.create_index(op.f("ix_repository_metadata_project_id"), "repository_metadata", ["project_id"], unique=False)

    op.create_table(
        "file_metadata",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=50), nullable=False),
        sa.Column("language", sa.String(length=50), nullable=True),
        sa.Column("lines_of_code", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_test_file", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_important", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("has_docstring", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("function_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("class_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("imports", postgresql.JSONB(), nullable=True),
        sa.Column("is_processed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("chunks_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["repository_id"], ["repository_metadata.id"]),
    )
    op.create_index(op.f("ix_file_metadata_id"), "file_metadata", ["id"], unique=False)
    op.create_index(op.f("ix_file_metadata_project_id"), "file_metadata", ["project_id"], unique=False)
    op.create_index(op.f("ix_file_metadata_repository_id"), "file_metadata", ["repository_id"], unique=False)

    op.create_table(
        "code_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("chunk_type", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=50), nullable=False),
        sa.Column("parent_chunk_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("embedding_model", sa.String(length=100), nullable=True),
        sa.Column("is_important", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("docstring", sa.Text(), nullable=True),
        sa.Column("dependencies", postgresql.JSONB(), nullable=True),
        sa.Column("parameters", postgresql.JSONB(), nullable=True),
        sa.Column("return_type", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["parent_chunk_id"], ["code_chunks.id"]),
    )
    op.create_index(op.f("ix_code_chunks_id"), "code_chunks", ["id"], unique=False)
    op.create_index(op.f("ix_code_chunks_project_id"), "code_chunks", ["project_id"], unique=False)

    op.create_table(
        "analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "PREPROCESSING", "ANALYZING", "PAUSED", "COMPLETED", "FAILED", "CANCELLED",
                    name="analysisstatus"),
            nullable=False,
        ),
        sa.Column(
            "current_stage",
            sa.Enum("REPO_SCAN", "CODE_CHUNKING", "EMBEDDING_GENERATION", "AGENT_ORCHESTRATION",
                    "DOCUMENTATION_GENERATION", "COMPLETED", name="analysisstage"),
            nullable=True,
        ),
        sa.Column("total_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_chunks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_chunks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("analysis_depth", sa.String(length=50), nullable=False, server_default="standard"),
        sa.Column("target_personas", postgresql.JSONB(), nullable=True),
        sa.Column("verbosity_level", sa.String(length=50), nullable=False, server_default="normal"),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("paused_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("user_context", postgresql.JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_analyses_id"), "analyses", ["id"], unique=False)
    op.create_index(op.f("ix_analyses_project_id"), "analyses", ["project_id"], unique=False)

    op.create_table(
        "analysis_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("stage", sa.String(length=100), nullable=True),
        sa.Column("current_file", sa.String(length=500), nullable=True),
        sa.Column("file_index", sa.Integer(), nullable=True),
        sa.Column("total_files", sa.Integer(), nullable=True),
        sa.Column("progress_percentage", sa.Float(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_analysis_logs_id"), "analysis_logs", ["id"], unique=False)
    op.create_index(op.f("ix_analysis_logs_analysis_id"), "analysis_logs", ["analysis_id"], unique=False)

    op.create_table(
        "analysis_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_type", sa.String(length=50), nullable=False),
        sa.Column("persona", sa.String(length=50), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("format", sa.String(length=50), nullable=False, server_default="markdown"),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_analysis_artifacts_id"), "analysis_artifacts", ["id"], unique=False)
    op.create_index(op.f("ix_analysis_artifacts_analysis_id"), "analysis_artifacts", ["analysis_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_analysis_artifacts_analysis_id"), table_name="analysis_artifacts")
    op.drop_index(op.f("ix_analysis_artifacts_id"), table_name="analysis_artifacts")
    op.drop_table("analysis_artifacts")

    op.drop_index(op.f("ix_analysis_logs_analysis_id"), table_name="analysis_logs")
    op.drop_index(op.f("ix_analysis_logs_id"), table_name="analysis_logs")
    op.drop_table("analysis_logs")

    op.drop_index(op.f("ix_analyses_project_id"), table_name="analyses")
    op.drop_index(op.f("ix_analyses_id"), table_name="analyses")
    op.drop_table("analyses")

    op.drop_index(op.f("ix_code_chunks_project_id"), table_name="code_chunks")
    op.drop_index(op.f("ix_code_chunks_id"), table_name="code_chunks")
    op.drop_table("code_chunks")

    op.drop_index(op.f("ix_file_metadata_repository_id"), table_name="file_metadata")
    op.drop_index(op.f("ix_file_metadata_project_id"), table_name="file_metadata")
    op.drop_index(op.f("ix_file_metadata_id"), table_name="file_metadata")
    op.drop_table("file_metadata")

    op.drop_index(op.f("ix_repository_metadata_project_id"), table_name="repository_metadata")
    op.drop_index(op.f("ix_repository_metadata_id"), table_name="repository_metadata")
    op.drop_table("repository_metadata")

    op.drop_index(op.f("ix_projects_id"), table_name="projects")
    op.drop_table("projects")

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_table("users")

    sa.Enum(name="analysisstage").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="analysisstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="projectstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="sourcetype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="userrole").drop(op.get_bind(), checkfirst=True)
    op.execute("DROP EXTENSION IF EXISTS vector")
