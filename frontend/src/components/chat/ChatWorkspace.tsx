import type { AssistantTask, ChatEntry, ModelSelection } from "../../types/api";
import { AgentTrace } from "../agents/AgentTrace";
import { QuizPanel } from "../quiz/QuizPanel";
import { CitationList } from "./CitationList";

const taskCopy: Record<AssistantTask, { label: string; hint: string; icon: string }> = {
  qa: { label: "Ask", hint: "Ask a grounded question", icon: "?" },
  summary: { label: "Summarize", hint: "Summarize selected documents", icon: "≡" },
  quiz: { label: "Quiz", hint: "Create a knowledge check", icon: "✓" },
};

interface Props {
  entries: ChatEntry[];
  task: AssistantTask;
  message: string;
  selectedCount: number;
  running: boolean;
  models: ModelSelection | null;
  onTask: (task: AssistantTask) => void;
  onMessage: (message: string) => void;
  onSubmit: () => void;
  onReset: () => void;
  onOpenModels: () => void;
}

export function ChatWorkspace(props: Props) {
  const canSubmit = props.selectedCount > 0 && props.message.trim() && !props.running;
  return (
    <main className="workspace">
      <header className="workspace-header">
        <div><span className="eyebrow">Grounded workspace</span><h1>Research with your documents</h1></div>
        <div className="workspace-actions">
          <button className="model-config-button" type="button" onClick={props.onOpenModels} disabled={!props.models} aria-label="Choose chat and embedding models">
            <span className="model-live-dot" />
            <span className="model-button-copy">
              <small>Models</small>
              <strong>{props.models ? `${props.models.chat.provider} · ${props.models.chat.model}` : "Loading…"}</strong>
            </span>
            <b>⌄</b>
          </button>
          <button className="new-chat" type="button" onClick={props.onReset} aria-label="Start a new thread">
            <span aria-hidden="true">＋</span><span>New thread</span>
          </button>
        </div>
      </header>

      <section className="messages" aria-live="polite">
        {props.entries.length === 0 && (
          <div className="welcome">
            <span className="welcome-orbit"><i>✦</i></span>
            <span className="eyebrow">Multi-agent document assistant</span>
            <h2>Turn your documents into answers.</h2>
            <p>Select one or more ready documents, then ask a question, request a summary, or generate a grounded quiz.</p>
            <div className="suggestions">
              {["What are the key findings?", "Summarize the main arguments", "Create a 5-question quiz"].map((text, index) => (
                <button key={text} type="button" onClick={() => {
                  props.onTask(index === 1 ? "summary" : index === 2 ? "quiz" : "qa");
                  props.onMessage(text);
                }}>{text}<span>↗</span></button>
              ))}
            </div>
          </div>
        )}
        {props.entries.map((entry) => (
          <article className={`message ${entry.role}`} key={entry.id}>
            <div className="avatar">{entry.role === "user" ? "YOU" : "A"}</div>
            <div className="message-content">
              <span className="message-author">{entry.role === "user" ? "You" : "Atlas"}</span>
              <p>{entry.text}</p>
              {entry.result?.quiz && <QuizPanel questions={entry.result.quiz.questions} />}
              {entry.result && !entry.result.quiz && <CitationList citations={entry.result.citations} />}
              {entry.result && <AgentTrace result={entry.result} />}
            </div>
          </article>
        ))}
        {props.running && (
          <div className="thinking"><span /><span /><span /> Retrieving and reviewing evidence</div>
        )}
      </section>

      <footer className="composer-shell">
        <div className="task-tabs">
          {(Object.keys(taskCopy) as AssistantTask[]).map((key) => (
            <button className={props.task === key ? "active" : ""} type="button" key={key} onClick={() => props.onTask(key)}>
              <span>{taskCopy[key].icon}</span>{taskCopy[key].label}
            </button>
          ))}
          <small>{props.selectedCount || "No"} document{props.selectedCount === 1 ? "" : "s"} in scope</small>
        </div>
        <div className="composer">
          <textarea
            value={props.message}
            rows={2}
            placeholder={taskCopy[props.task].hint}
            onChange={(event) => props.onMessage(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                if (canSubmit) props.onSubmit();
              }
            }}
          />
          <button type="button" disabled={!canSubmit} onClick={props.onSubmit} aria-label="Send request">↑</button>
        </div>
        <p className="composer-note">Answers are generated only from selected evidence. Verify critical information.</p>
      </footer>
    </main>
  );
}
