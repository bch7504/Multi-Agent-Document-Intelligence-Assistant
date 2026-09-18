"""Add saved quiz library and attempts.

Revision ID: 20260917_0005
Revises: 20260917_0004
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260917_0005"
down_revision: str | None = "20260917_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quizzes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("questions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["assistant_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_index("ix_quizzes_conversation_id", "quizzes", ["conversation_id"])
    op.create_index("ix_quizzes_created_at", "quizzes", ["created_at"])
    op.create_table(
        "quiz_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("quiz_id", sa.Uuid(), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=False),
        sa.Column("total_questions", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["quiz_id"], ["quizzes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quiz_attempts_quiz_id", "quiz_attempts", ["quiz_id"])
    op.create_index("ix_quiz_attempts_created_at", "quiz_attempts", ["created_at"])

    connection = op.get_bind()
    runs = connection.execute(
        sa.text(
            "SELECT id, conversation_id, quiz, created_at "
            "FROM assistant_runs WHERE quiz IS NOT NULL"
        )
    ).mappings()
    for run in runs:
        quiz = run["quiz"]
        questions = quiz.get("questions", []) if isinstance(quiz, dict) else []
        if not questions:
            continue
        insert_quiz = sa.text(
                "INSERT INTO quizzes "
                "(id, run_id, conversation_id, title, questions, created_at, updated_at) "
                "VALUES (:id, :run_id, :conversation_id, :title, :questions, :created_at, :updated_at)"
            ).bindparams(sa.bindparam("questions", type_=sa.JSON()))
        connection.execute(
            insert_quiz,
            {
                "id": run["id"],
                "run_id": run["id"],
                "conversation_id": run["conversation_id"],
                "title": "Imported quiz",
                "questions": questions,
                "created_at": run["created_at"],
                "updated_at": run["created_at"],
            },
        )


def downgrade() -> None:
    op.drop_index("ix_quiz_attempts_created_at", table_name="quiz_attempts")
    op.drop_index("ix_quiz_attempts_quiz_id", table_name="quiz_attempts")
    op.drop_table("quiz_attempts")
    op.drop_index("ix_quizzes_created_at", table_name="quizzes")
    op.drop_index("ix_quizzes_conversation_id", table_name="quizzes")
    op.drop_table("quizzes")
