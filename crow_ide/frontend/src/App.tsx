import { useState, useEffect } from 'react'
import { useAtom } from 'jotai'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { FileTree } from './components/FileTree'
import { TabbedTerminal } from './components/TabbedTerminal'
import { WorkspaceSelector } from './components/WorkspaceSelector'
import AgentPanel from './components/acp/agent-panel'
import { workspaceAtom } from './components/acp/state'
import { setCurrentWorkspace } from './components/acp/adapters'
import './App.css'

function App() {
  const [workspace] = useAtom(workspaceAtom)
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [filesExpanded, setFilesExpanded] = useState(true)
  const [terminalExpanded, setTerminalExpanded] = useState(true)

  // Sync workspace to adapters module when it changes
  useEffect(() => {
    setCurrentWorkspace(workspace)
  }, [workspace])

  return (
    <div className="crow-app">
      {/* Header with workspace selector */}
      <header className="crow-header">
        <WorkspaceSelector />
        <span className="crow-header-title">Crow IDE</span>
      </header>

      {/* Main content area */}
      <div className="crow-main">
        {/* Left: Agent Panel - Full Height */}
        <div className="crow-agent-section" data-testid="agent-panel">
          <AgentPanel />
        </div>

      {/* Right: Workspace (Editor + Files side-by-side, Terminal below) */}
      <div className="crow-workspace">
        {/* Top area: Editor and Files side by side */}
        <div className="crow-top-area">
          {/* Editor Area - Shows selected file or placeholder */}
          <div className="crow-editor-section" data-testid="editor">
            <div className="crow-section-header">
              <span className="crow-section-title">
                {selectedFile ? selectedFile.split('/').pop() : 'Editor'}
              </span>
            </div>
            <div className="crow-editor-content">
              {selectedFile ? (
                <div className="crow-file-preview">
                  <code>{selectedFile}</code>
                </div>
              ) : (
                <div className="crow-editor-placeholder">
                  <div className="crow-placeholder-icon">📄</div>
                  <p>Select a file to view</p>
                  <p className="crow-hint">Files modified by the agent will appear here</p>
                </div>
              )}
            </div>
          </div>

          {/* File Explorer - Right side, collapsible */}
          <div
            className={`crow-files-section ${filesExpanded ? '' : 'collapsed'}`}
            data-testid="file-tree"
          >
            <div
              className="crow-section-header crow-collapsible-header"
              onClick={() => setFilesExpanded(!filesExpanded)}
            >
              <span className="crow-section-title">
                {filesExpanded ? (
                  <ChevronDown className="crow-collapse-icon" size={14} />
                ) : (
                  <ChevronRight className="crow-collapse-icon" size={14} />
                )}
                Files
              </span>
            </div>
            {filesExpanded && (
              <div className="crow-files-content">
                <FileTree onFileSelect={setSelectedFile} />
              </div>
            )}
          </div>
        </div>

        {/* Terminal - Bottom of workspace */}
        <div
          className={`crow-terminal-section ${terminalExpanded ? '' : 'collapsed'}`}
          data-testid="terminal"
        >
          <div
            className="crow-section-header crow-collapsible-header"
            onClick={() => setTerminalExpanded(!terminalExpanded)}
          >
            <span className="crow-section-title">
              {terminalExpanded ? (
                <ChevronDown className="crow-collapse-icon" size={14} />
              ) : (
                <ChevronRight className="crow-collapse-icon" size={14} />
              )}
              Terminal
            </span>
          </div>
          {terminalExpanded && (
            <div className="crow-terminal-content">
              <TabbedTerminal />
            </div>
          )}
        </div>
      </div>
      </div>
    </div>
  )
}

export default App
