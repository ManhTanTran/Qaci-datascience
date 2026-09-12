import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import "./ai-insight.css";
import "./agent-demo.css";
import "./flow.css";
import "./harness-dark.css";
import AdminApp from "./AdminApp";
import AgentDemoApp from "./AgentDemoApp";
import ReasoningWorkspaceApp from "./ReasoningWorkspaceApp";

const isAdmin = window.location.pathname.startsWith("/admin");
const isAgentDemo = window.location.pathname.startsWith("/agent-demo");
createRoot(document.getElementById("root")!).render(<StrictMode>{isAdmin ? <AdminApp /> : isAgentDemo ? <AgentDemoApp /> : <ReasoningWorkspaceApp />}</StrictMode>);
