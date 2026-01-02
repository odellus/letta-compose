import { FileTree } from './components/FileTree'
import { Terminal } from './components/Terminal'
import { AgentPanel } from './components/AgentPanel'
import './App.css'

function App() {
  return (
    <div className="app">
      <div className="sidebar" data-testid="file-tree">
        <FileTree />
      </div>
      <div className="main">
        <div className="editor-area">
          <div className="agent-panel" data-testid="agent-panel">
            <AgentPanel />
          </div>
        </div>
        <div className="terminal-area" data-testid="terminal">
          <Terminal />
        </div>
      </div>
    </div>
  )
}

export default App
