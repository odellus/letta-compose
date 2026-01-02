import { useState, useEffect } from 'react'
import './FileTree.css'

interface FileEntry {
  name: string
  path: string
  is_directory: boolean
  size: number
}

export function FileTree() {
  const [files, setFiles] = useState<FileEntry[]>([])
  const [currentPath, setCurrentPath] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadFiles()
  }, [currentPath])

  const loadFiles = async () => {
    setLoading(true)
    try {
      const response = await fetch('/api/files/list', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(currentPath ? { path: currentPath } : {}),
      })
      const data = await response.json()
      setFiles(data.files || [])
    } catch (error) {
      console.error('Failed to load files:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleClick = (file: FileEntry) => {
    if (file.is_directory) {
      setCurrentPath(file.path)
    }
  }

  if (loading) {
    return <div className="file-tree loading">Loading...</div>
  }

  return (
    <div className="file-tree">
      <div className="file-tree-header">
        <span>Files</span>
      </div>
      <ul className="file-list">
        {currentPath && (
          <li
            className="file-item directory"
            onClick={() => setCurrentPath('')}
          >
            📁 ..
          </li>
        )}
        {files.map((file) => (
          <li
            key={file.path}
            className={`file-item ${file.is_directory ? 'directory' : 'file'}`}
            onClick={() => handleClick(file)}
          >
            {file.is_directory ? '📁' : '📄'} {file.name}
          </li>
        ))}
      </ul>
    </div>
  )
}
