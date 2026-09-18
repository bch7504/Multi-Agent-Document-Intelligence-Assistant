import { useEffect, useState } from "react";
import {
  deleteQuiz,
  getQuiz,
  listQuizAttempts,
  submitQuizAttempt,
} from "../../services/api";
import type { QuizAttempt, QuizLibraryItem, SavedQuiz } from "../../types/api";
import { CitationList } from "../chat/CitationList";

interface Props {
  open: boolean;
  loading: boolean;
  quizzes: QuizLibraryItem[];
  onRefresh: () => Promise<void>;
  onClose: () => void;
  onError: (message: string) => void;
  onNotice: (message: string) => void;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

export function QuizLibrary(props: Props) {
  const [selected, setSelected] = useState<SavedQuiz | null>(null);
  const [attempts, setAttempts] = useState<QuizAttempt[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [result, setResult] = useState<QuizAttempt | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!props.open) {
      setSelected(null);
      setAnswers({});
      setResult(null);
    }
  }, [props.open]);

  if (!props.open) return null;

  async function openQuiz(id: string) {
    setBusy(true);
    try {
      const [quiz, history] = await Promise.all([getQuiz(id), listQuizAttempts(id)]);
      setSelected(quiz);
      setAttempts(history.items);
      setAnswers({});
      setResult(null);
    } catch (cause) {
      props.onError(cause instanceof Error ? cause.message : "Could not load quiz");
    } finally {
      setBusy(false);
    }
  }

  async function submitAttempt() {
    if (!selected) return;
    setBusy(true);
    try {
      const attempt = await submitQuizAttempt(selected.id, answers);
      setResult(attempt);
      setAttempts((items) => [attempt, ...items]);
      await props.onRefresh();
      props.onNotice(`Quiz submitted · ${attempt.scorePercent}%`);
    } catch (cause) {
      props.onError(cause instanceof Error ? cause.message : "Could not submit quiz");
    } finally {
      setBusy(false);
    }
  }

  async function removeQuiz(id: string) {
    if (!window.confirm("Delete this quiz and all attempts?")) return;
    try {
      await deleteQuiz(id);
      if (selected?.id === id) setSelected(null);
      await props.onRefresh();
      props.onNotice("Quiz deleted");
    } catch (cause) {
      props.onError(cause instanceof Error ? cause.message : "Could not delete quiz");
    }
  }

  const complete = selected ? Object.keys(answers).length === selected.questions.length : false;

  return (
    <div className="library-backdrop" role="presentation" onMouseDown={props.onClose}>
      <section className="library-panel quiz-library" role="dialog" aria-modal="true" aria-label="Quiz library" onMouseDown={(event) => event.stopPropagation()}>
        <header>
          <div>
            <span className="eyebrow">Learning workspace</span>
            <h2>{selected ? selected.title : "Quiz library"}</h2>
          </div>
          <div className="library-header-actions">
            {selected && <button type="button" className="back-button" onClick={() => setSelected(null)}>← All quizzes</button>}
            <button className="dialog-close" type="button" onClick={props.onClose}>×</button>
          </div>
        </header>

        <div className="library-body">
          {(props.loading || busy) && !selected && <div className="library-empty">Loading quizzes…</div>}
          {!selected && !props.loading && props.quizzes.length === 0 && (
            <div className="library-empty"><strong>No saved quizzes yet</strong><span>Generate a quiz from the chat workspace to add it here.</span></div>
          )}
          {!selected && props.quizzes.map((quiz) => (
            <article className="quiz-library-row" key={quiz.id}>
              <button type="button" className="quiz-library-open" onClick={() => void openQuiz(quiz.id)}>
                <span className="quiz-library-icon">Q</span>
                <span><strong>{quiz.title}</strong><small>{quiz.questionCount} questions · {quiz.attemptCount} attempts · {formatDate(quiz.createdAt)}</small></span>
                <b>{quiz.bestScorePercent === null ? "New" : `${quiz.bestScorePercent}% best`}</b>
              </button>
              <button className="library-delete" type="button" onClick={() => void removeQuiz(quiz.id)}>Delete</button>
            </article>
          ))}

          {selected && (
            <div className="saved-quiz-detail">
              {selected.questions.map((question, index) => (
                <article className="quiz-card" key={question.id}>
                  <span className="question-number">Question {index + 1}</span>
                  <h3>{question.question}</h3>
                  <div className="quiz-options">
                    {question.options.map((option) => {
                      const chosen = answers[question.id] === option.id;
                      const correct = Boolean(result) && option.id === question.correctOptionId;
                      const wrong = Boolean(result) && chosen && !correct;
                      return (
                        <button
                          type="button"
                          disabled={Boolean(result)}
                          className={`${chosen ? "chosen" : ""} ${correct ? "correct" : ""} ${wrong ? "wrong" : ""}`}
                          key={option.id}
                          onClick={() => setAnswers((items) => ({ ...items, [question.id]: option.id }))}
                        >
                          <span>{option.id}</span>{option.text}
                        </button>
                      );
                    })}
                  </div>
                  {result && (
                    <div className="quiz-explanation">
                      <strong>{answers[question.id] === question.correctOptionId ? "Correct" : "Review the answer"}</strong>
                      <p>{question.explanation}</p>
                      <CitationList citations={question.citations} />
                    </div>
                  )}
                </article>
              ))}
              {!result ? (
                <button className="submit-attempt" type="button" disabled={!complete || busy} onClick={() => void submitAttempt()}>
                  {complete ? "Submit answers" : `Answer ${selected.questions.length - Object.keys(answers).length} more`}
                </button>
              ) : (
                <div className="attempt-result"><strong>{result.scorePercent}%</strong><span>{result.correctCount}/{result.totalQuestions} correct</span><button type="button" onClick={() => { setAnswers({}); setResult(null); }}>Try again</button></div>
              )}
              {attempts.length > 0 && (
                <div className="attempt-history">
                  <h3>Attempt history</h3>
                  {attempts.map((attempt) => <div key={attempt.id}><span>{formatDate(attempt.createdAt)}</span><strong>{attempt.scorePercent}%</strong></div>)}
                </div>
              )}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
