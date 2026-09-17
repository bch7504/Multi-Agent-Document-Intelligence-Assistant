import { useState } from "react";
import type { QuizQuestion } from "../../types/api";
import { CitationList } from "../chat/CitationList";

function QuizCard({ question, index }: { question: QuizQuestion; index: number }) {
  const [selected, setSelected] = useState<string | null>(null);
  const answered = selected !== null;
  return (
    <article className="quiz-card">
      <span className="question-number">Question {index + 1}</span>
      <h3>{question.question}</h3>
      <div className="quiz-options">
        {question.options.map((option) => {
          const correct = answered && option.id === question.correctOptionId;
          const wrong = answered && selected === option.id && !correct;
          return (
            <button
              type="button"
              disabled={answered}
              className={`${correct ? "correct" : ""} ${wrong ? "wrong" : ""}`}
              key={option.id}
              onClick={() => setSelected(option.id)}
            >
              <span>{option.id}</span>{option.text}
            </button>
          );
        })}
      </div>
      {answered && (
        <div className="quiz-explanation">
          <strong>{selected === question.correctOptionId ? "Correct" : "Review the answer"}</strong>
          <p>{question.explanation}</p>
          <CitationList citations={question.citations} />
        </div>
      )}
    </article>
  );
}

export function QuizPanel({ questions }: { questions: QuizQuestion[] }) {
  return <div className="quiz-grid">{questions.map((q, index) => <QuizCard key={q.id} question={q} index={index} />)}</div>;
}
