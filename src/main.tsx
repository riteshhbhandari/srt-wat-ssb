import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronRight,
  Clock3,
  Download,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import type { SRTQuestion } from "./data/srtQuestions";
import { testWords } from "./data/words";
import { generateWords } from "./services/wordGenerator";
import { analyzeSRTResponses, type Analysis } from "./services/llm";
import { generateSRTQuestions } from "./services/srtGenerator";
import { downloadWordList, downloadAnalysisReport } from "./services/pdfGenerator";
import "./styles.css";

type Screen =
  | "landing"
  | "srt-intro"
  | "srt-test"
  | "srt-complete"
  | "analysis"
  | "word-intro"
  | "word-test"
  | "word-complete";
const format = (sec: number) =>
  `${String(Math.floor(sec / 60)).padStart(2, "0")}:${String(sec % 60).padStart(2, "0")}`;
const averageWords = (answers: Record<number, string>) => {
  const a = Object.values(answers).filter(Boolean);
  return Math.round(
    a.reduce((t, x) => t + x.trim().split(/\s+/).filter(Boolean).length, 0) /
      Math.max(a.length, 1),
  );
};
function App() {
  const [screen, setScreen] = useState<Screen>("landing"),
    [index, setIndex] = useState(0),
    [questions, setQuestions] = useState<SRTQuestion[]>([]),
    [answers, setAnswers] = useState<Record<number, string>>(() =>
      JSON.parse(localStorage.getItem("ssb-srt-answers") || "{}"),
    ),
    [remaining, setRemaining] = useState(1800),
    [started, setStarted] = useState<number | null>(null),
    [expired, setExpired] = useState(false),
    [analysis, setAnalysis] = useState<Analysis | null>(null),
    [wordIndex, setWordIndex] = useState(0),
    [words, setWords] = useState<string[]>(testWords);
  const wordStart = useRef(0);
  const [wordCount, setWordCount] = useState(15);
  const [analyzing, setAnalyzing] = useState(false);
  useEffect(() => {
    localStorage.setItem("ssb-srt-answers", JSON.stringify(answers));
  }, [answers]);
  useEffect(() => {
    if (screen !== "srt-test" || !started) return;
    const tick = () => {
      const left = Math.max(
        0,
        Math.ceil((1800000 - (Date.now() - started)) / 1000),
      );
      setRemaining(left);
      if (!left) {
        setExpired(true);
        setScreen("srt-complete");
      }
    };
    tick();
    const id = setInterval(tick, 250);
    return () => clearInterval(id);
  }, [screen, started]);
  useEffect(() => {
    if (screen !== "word-test") return;
    wordStart.current = performance.now();
    setWordCount(15);
    let raf: number;
    const step = () => {
      const elapsed = performance.now() - wordStart.current;
      const n = Math.floor(elapsed / 15000);
      if (n >= 60) {
        setScreen("word-complete");
        return;
      }
      setWordIndex(n);
      setWordCount(Math.max(0, 15 - Math.floor((elapsed - n * 15000) / 1000)));
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [screen]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (screen === "srt-test") {
        if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
          e.preventDefault();
          setScreen("srt-complete");
        }
        if (e.key === "ArrowLeft" && index > 0) setIndex(index - 1);
        if (e.key === "ArrowRight" && index < 59) setIndex(index + 1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [screen, index]);
  const startSRT = async () => {
    const fresh = await generateSRTQuestions();
    setQuestions(fresh);
    setAnswers({});
    const now = Date.now();
    setStarted(now);
    setRemaining(1800);
    setExpired(false);
    setIndex(0);
    setScreen("srt-test");
    localStorage.setItem(
      "ssb-srt-session",
      JSON.stringify({ type: "SRT", startTime: now, completion: false }),
    );
  };
  const startWordTest = async () => {
    const fresh = await generateWords();
    setWords(fresh);
    setWordIndex(0);
    setScreen("word-test");
  };
  const submit = () => {
    setScreen("srt-complete");
    localStorage.setItem(
      "ssb-srt-session",
      JSON.stringify({
        type: "SRT",
        startTime: started,
        endTime: Date.now(),
        responses: answers,
        completion: true,
      }),
    );
  };
  const doAnalysis = async () => {
    setAnalyzing(true);
    try {
      setAnalysis(await analyzeSRTResponses(answers, questions));
      setScreen("analysis");
    } catch (e) {
      alert(e instanceof Error ? e.message : "Unable to analyse responses.");
    } finally {
      setAnalyzing(false);
    }
  };
  const done = Object.values(answers).filter((x) => x.trim()).length;
  if (screen === "landing") return <Landing go={setScreen} />;
  if (screen === "srt-intro" || screen === "word-intro") {
    const word = screen === "word-intro";
    return (
      <Intro
        word={word}
        back={() => setScreen("landing")}
        start={word ? startWordTest : startSRT}
      />
    );
  }
  if (screen === "srt-test") {
    const q = questions[index];
    return (
      <main className="exam">
        <header className="exambar">
          <span>SRT</span>
          <span>Situation {String(index + 1).padStart(2, "0")} / 60</span>
          <span
            className={
              remaining < 60 ? "urgent" : remaining < 300 ? "warning" : ""
            }
          >
            {format(remaining)}
          </span>
        </header>
        <section className="question">
          <p className="eyebrow">SITUATION {String(q.id).padStart(2, "0")}</p>
          <h1>{q.situation}</h1>
          <textarea
            autoFocus
            placeholder="What would you do?"
            value={answers[q.id] || ""}
            onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })}
          />
        </section>
        <footer className="examfoot">
          <button
            className="textbtn"
            disabled={!index}
            onClick={() => setIndex(index - 1)}
          >
            <ArrowLeft />
            Previous
          </button>
          <div className="dots">
            {questions.map((q, i) => (
              <button
                key={q.id}
                onClick={() => setIndex(i)}
                className={`${i === index ? "current" : ""} ${answers[q.id] ? "answered" : ""}`}
              >
                {String(q.id).padStart(2, "0")}
              </button>
            ))}
          </div>
          {index === 59 ? (
            <button className="darkbtn" onClick={submit}>
              Submit test <Check />
            </button>
          ) : (
            <button className="textbtn" onClick={() => setIndex(index + 1)}>
              Next
              <ArrowRight />
            </button>
          )}
        </footer>
      </main>
    );
  }
  if (screen === "srt-complete")
    return (
      <Complete
        answered={done}
        time={format(1800 - remaining)}
        expired={expired}
        onAnalysis={doAnalysis}
        restart={() => setScreen("landing")}
        analyzing={analyzing}
      />
    );
    if (screen === "analysis" && analysis)
    return (
      <AnalysisView
        data={analysis}
        back={() => setScreen("landing")}
        questions={questions}
        responses={answers}
      />
    );
  if (screen === "word-test")
    return (
      <main className="word">
        <span className={`wordtimer${wordCount <= 3 ? " urgent" : ""}`}>
          {String(wordCount).padStart(2, "0")}s
        </span>
        <h1 key={wordIndex}>{words[wordIndex] ?? testWords[wordIndex]}</h1>
        <small>{wordIndex + 1} / 60</small>
      </main>
    );
  return (
    <main className="complete">
      <div className="complete-mark">
        <Check />
      </div>
      <p className="eyebrow">WORD TEST</p>
      <h1>Test Complete</h1>
      <div className="stats">
        <div>
          <b>60 / 60</b>
          <span>words completed</span>
        </div>
        <div>
          <b>15:00</b>
          <span>total time</span>
        </div>
      </div>
      <div className="actions">
        <button
          className="darkbtn"
          onClick={() =>
            downloadWordList(words).catch(() =>
              alert("Download failed. Is the server running?"),
            )
          }
        >
          <Download />
          Download Word List
        </button>
        <button className="outlinebtn" onClick={() => setScreen("word-intro")}>
          <RotateCcw />
          Practice Again
        </button>
      </div>
    </main>
  );
}
function Landing({ go }: { go: (s: Screen) => void }) {
  return (
    <main className="landing">
      <nav>
        <span className="brand">SSB PRACTICE</span>
        <div>
          <button onClick={() => go("srt-intro")}>SRT</button>
          <button onClick={() => go("word-intro")}>Word Test</button>
          {/* <button>History</button> */}
        </div>
      </nav>
      <section className="hero">
        <p className="eyebrow">INDIAN ARMED FORCES · PSYCHOLOGICAL PRACTICE</p>
        <h1>
          Train for the test.
          <br />
          Understand your response.
        </h1>
        <p className="lead">
          Practice SSB psychological tests under realistic time constraints and
          use focused feedback to identify where your responses can improve.
        </p>
        <div className="test-options">
          <button onClick={() => go("srt-intro")}>
            <span className="eyebrow">SRT</span>
            <h2>Situation Reaction Test</h2>
            <p>60 situations · 30 minutes</p>
            <strong>
              Start SRT <ChevronRight />
            </strong>
          </button>
          <button onClick={() => go("word-intro")}>
            <span className="eyebrow">WORD TEST</span>
            <h2>60-word timed response test</h2>
            <p>60 words · 15 seconds each</p>
            <strong>
              Start Word Association Test <ChevronRight />
            </strong>
          </button>
        </div>
        </section>
        <footer>
          <span className="eyebrow">A LIFE LIVED LESS ORDINARY</span>
        </footer>
      </main>
    );
  }
function Intro({
  word,
  back,
  start,
}: {
  word: boolean;
  back: () => void;
  start: () => void | Promise<void>;
}) {
  const [loading, setLoading] = useState(false),
    [error, setError] = useState("");
  const begin = async () => {
    setLoading(true);
    setError("");
    try {
      await start();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Unable to generate questions.",
      );
    } finally {
      setLoading(false);
    }
  };
  return (
    <main className="intro">
      <button className="back" onClick={back}>
        <ArrowLeft /> Back
      </button>
      <div>
        <p className="eyebrow">
          {word ? "WORD ASSOCIATION PRACTICE" : "SSB PSYCHOLOGICAL PRACTICE"}
        </p>
        <h1>{word ? "60-Word Test" : "Situation Reaction Test"}</h1>
        <div className="ruleline">
          <span>{word ? "60 Words" : "60 Situations"}</span>
          <i />
          <span>{word ? "15 Seconds / Word" : "30 Minutes"}</span>
          {word && (
            <>
              <i />
              <span>15 Minutes Total</span>
            </>
          )}
        </div>
        <p>
          {word
            ? "A fresh set of 60 words is generated by Gemini before each attempt. A word will appear on screen for exactly 15 seconds. Respond naturally and move on mentally when the word changes."
            : "Generate a fresh, varied set of 60 situations before each practice attempt using Gemini."}
        </p>
        {error && (
          <div className="generator">
            <small>{error}</small>
          </div>
        )}
        <button className="darkbtn" disabled={loading} onClick={begin}>
          {loading
            ? word
              ? "Generating 60 words…"
              : "Generating 60 situations…"
            : "Start Test"}{" "}
          <ArrowRight />
        </button>
      </div>
    </main>
  );
}
function Complete({
  answered,
  time,
  expired,
  onAnalysis,
  restart,
  analyzing,
}: {
  answered: number;
  time: string;
  expired: boolean;
  onAnalysis: () => void;
  restart: () => void;
  analyzing: boolean;
}) {
  return (
    <main className="complete">
      <div className="complete-mark">
        <Check />
      </div>
      <p className="eyebrow">SRT · {expired ? "TIME EXPIRED" : "SUBMITTED"}</p>
      <h1>{expired ? "Time expired" : "Test Complete"}</h1>
      <div className="stats">
        <div>
          <b>{answered} / 60</b>
          <span>situations answered</span>
        </div>
        <div>
          <b>{time}</b>
          <span>time used</span>
        </div>
        <div>
          <b>
            {averageWords(
              JSON.parse(localStorage.getItem("ssb-srt-answers") || "{}"),
            )}
          </b>
          <span>average words</span>
        </div>
      </div>
      <div className="actions">
        <button
          className="darkbtn"
          disabled={analyzing}
          onClick={onAnalysis}
        >
          {analyzing ? "Analysing responses…" : "Analyse My Performance"}{" "}
          <ChevronRight />
        </button>
        <button className="outlinebtn" onClick={restart}>
          Return home
        </button>
      </div>
    </main>
  );
}
function AnalysisView({ data, back, questions, responses }: {
  data: Analysis;
  back: () => void;
  questions: SRTQuestion[];
  responses: Record<number, string>;
}) {
  return (
    <main className="analysis">
      <nav>
        <span className="brand">SSB PRACTICE</span>
        <div>
          <button onClick={back}>Exit analysis</button>
          <button
            className="textbtn"
            onClick={() =>
              downloadAnalysisReport(questions, responses, data).catch(() =>
                alert("Download failed. Is the server running?"),
              )
            }
          >
            <Download />
            Download Report
          </button>
        </div>
      </nav>
      <header>
        <p className="eyebrow">PRACTICE FEEDBACK</p>
        <h1>Overall Assessment</h1>
        <p className="summary">{data.summary}</p>
        <small>
          <ShieldCheck /> AI-generated practice feedback only. This is not an
          official SSB psychological assessment and does not predict selection.
        </small>
      </header>
      <section>
        <h2>Performance dimensions</h2>
        <div className="dimensions">
          {data.dimensions.map((x) => (
            <div key={x.name}>
              <span>{x.name}</span>
              <div>
                <i style={{ width: `${x.score}%` }} />
              </div>
              <b>{x.score}</b>
            </div>
          ))}
        </div>
      </section>
      <section className="feedback">
        <div>
          <h2>What you did well</h2>
          <ul>
            {data.strengths.map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
        </div>
        <div>
          <h2>Where you can improve</h2>
          <ul>
            {data.improvements.map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
        </div>
      </section>
      <section>
        <h2>Situation-by-situation</h2>
        {data.items.map((x) => (
          <article className="item" key={x.id}>
            <p className="eyebrow">SITUATION {String(x.id).padStart(2, "0")}</p>
            <h3>{x.situation}</h3>
            <div>
              <p>
                <b>Your response</b>
                {x.response}
              </p>
              <p>
                <b>Score</b>
                <b className="score">{x.score} / 10</b>
              </p>
              <p>
                <b>Feedback</b>
                {x.feedback}
              </p>
              <p>
                <b>How to improve</b>
                {x.improvement}
              </p>
            </div>
          </article>
        ))}
      </section>
    </main>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
