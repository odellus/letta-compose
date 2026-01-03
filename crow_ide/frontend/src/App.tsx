import { useState, useEffect, useCallback } from 'react'
import { useAtom } from 'jotai'
import { ChevronDown, ChevronRight, Save } from 'lucide-react'
import { FileTree } from './components/FileTree'
import { TabbedTerminal } from './components/TabbedTerminal'
import { WorkspaceSelector } from './components/WorkspaceSelector'
import { CodeHighlighter } from './components/CodeHighlighter'
import AgentPanel from './components/acp/agent-panel'
import { workspaceAtom } from './components/acp/state'
import { setCurrentWorkspace } from './components/acp/adapters'
import './App.css'

function App() {
  const [workspace] = useAtom(workspaceAtom)
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [fileContent, setFileContent] = useState<string | null>(null)
  const [editedContent, setEditedContent] = useState<string | null>(null)
  const [fileLoading, setFileLoading] = useState(false)
  const [fileSaving, setFileSaving] = useState(false)
  const [fileError, setFileError] = useState<string | null>(null)
  const [filesExpanded, setFilesExpanded] = useState(true)
  const [terminalExpanded, setTerminalExpanded] = useState(true)

  // Check if file has unsaved changes
  const isDirty = editedContent !== null && editedContent !== fileContent

  // Save file function
  const saveFile = useCallback(async () => {
    if (!selectedFile || editedContent === null || !isDirty) return

    setFileSaving(true)
    try {
      const response = await fetch('/api/files/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: selectedFile, contents: editedContent }),
      })
      if (response.ok) {
        setFileContent(editedContent)
      } else {
        const data = await response.json()
        setFileError(data.error || 'Failed to save file')
      }
    } catch (err) {
      setFileError('Failed to save file')
    } finally {
      setFileSaving(false)
    }
  }, [selectedFile, editedContent, isDirty])

  // Handle Ctrl+S to save
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault()
        saveFile()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [saveFile])

  // Sync workspace to adapters module when it changes
  useEffect(() => {
    setCurrentWorkspace(workspace)
  }, [workspace])

  // Load file content when a file is selected
  useEffect(() => {
    if (!selectedFile) {
      setFileContent(null)
      setEditedContent(null)
      setFileError(null)
      return
    }

    const loadFile = async () => {
      setFileLoading(true)
      setFileError(null)
      setEditedContent(null)
      try {
        const response = await fetch('/api/files/details', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: selectedFile }),
        })
        const data = await response.json()
        if (response.ok && data.contents !== undefined) {
          setFileContent(data.contents)
          setEditedContent(data.contents)
        } else {
          setFileError(data.error || 'Failed to load file')
        }
      } catch (err) {
        setFileError('Failed to load file')
      } finally {
        setFileLoading(false)
      }
    }

    loadFile()
  }, [selectedFile])

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
                {isDirty && <span className="crow-dirty-indicator">●</span>}
              </span>
              {selectedFile && (
                <button
                  className="crow-save-button"
                  onClick={saveFile}
                  disabled={!isDirty || fileSaving}
                  title="Save (Ctrl+S)"
                >
                  <Save size={14} />
                  {fileSaving ? 'Saving...' : 'Save'}
                </button>
              )}
            </div>
            <div className="crow-editor-content">
              {selectedFile ? (
                <div className="crow-file-preview">
                  {fileLoading ? (
                    <div className="crow-file-loading">Loading...</div>
                  ) : fileError ? (
                    <div className="crow-file-error">{fileError}</div>
                  ) : (
                    <CodeHighlighter
                      code={editedContent || ''}
                      filename={selectedFile}
                      onChange={setEditedContent}
                    />
                  )}
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
