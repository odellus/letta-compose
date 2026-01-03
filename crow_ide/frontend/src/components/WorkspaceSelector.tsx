/* Crow IDE Workspace Selector */
import { useState, useEffect } from 'react';
import { useAtom } from 'jotai';
import { FolderOpen, Folder, AlertCircle } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from './ui/dialog';
import { Button } from './ui/button';
import { Input } from './ui/input';
import {
  workspaceAtom,
  recentWorkspacesAtom,
  addRecentWorkspace,
  getWorkspaceBasename,
  shortenWorkspacePath,
} from './acp/state';

interface WorkspaceSelectorProps {
  className?: string;
}

export function WorkspaceSelector({ className }: WorkspaceSelectorProps) {
  const [workspace, setWorkspace] = useAtom(workspaceAtom);
  const [recentWorkspaces, setRecentWorkspaces] = useAtom(recentWorkspacesAtom);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [pathInput, setPathInput] = useState(workspace || '');
  const [error, setError] = useState<string | null>(null);
  const [validating, setValidating] = useState(false);

  // Open dialog on first launch if no workspace
  useEffect(() => {
    if (!workspace) {
      setDialogOpen(true);
    }
  }, [workspace]);

  // Reset input when dialog opens
  useEffect(() => {
    if (dialogOpen) {
      setPathInput(workspace || '');
      setError(null);
    }
  }, [dialogOpen, workspace]);

  const validateAndOpenWorkspace = async (path: string) => {
    if (!path.trim()) {
      setError('Please enter a path');
      return;
    }

    setValidating(true);
    setError(null);

    try {
      const response = await fetch('/api/directories/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: path.trim() }),
      });

      const data = await response.json();

      if (response.ok && data.valid) {
        const expandedPath = data.path;
        setWorkspace(expandedPath);
        setRecentWorkspaces(addRecentWorkspace(recentWorkspaces, expandedPath));
        setDialogOpen(false);
      } else {
        setError(data.error || 'Invalid directory path');
      }
    } catch {
      setError('Failed to validate path');
    } finally {
      setValidating(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !validating) {
      validateAndOpenWorkspace(pathInput);
    }
  };

  const selectRecentWorkspace = (path: string) => {
    setPathInput(path);
    validateAndOpenWorkspace(path);
  };

  return (
    <>
      <button
        onClick={() => setDialogOpen(true)}
        className={`workspace-button flex items-center gap-2 px-3 py-1.5 rounded-md
          bg-gray-800 hover:bg-gray-700 text-gray-200 text-sm
          border border-gray-700 transition-colors ${className || ''}`}
      >
        <FolderOpen className="h-4 w-4" />
        <span className="max-w-[200px] truncate">
          {workspace ? getWorkspaceBasename(workspace) : 'Open Workspace'}
        </span>
      </button>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Open Workspace</DialogTitle>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <label htmlFor="path" className="text-sm font-medium text-gray-300">
                Path
              </label>
              <Input
                id="path"
                value={pathInput}
                onChange={(e) => setPathInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="/path/to/project"
                className="bg-gray-900 border-gray-600"
                autoFocus
              />
              {error && (
                <div className="flex items-center gap-2 text-red-400 text-sm">
                  <AlertCircle className="h-4 w-4" />
                  {error}
                </div>
              )}
            </div>

            {recentWorkspaces.length > 0 && (
              <div className="space-y-2">
                <label className="text-sm font-medium text-gray-400">
                  Recent Workspaces
                </label>
                <div className="space-y-1">
                  {recentWorkspaces.map((recentPath) => (
                    <button
                      key={recentPath}
                      onClick={() => selectRecentWorkspace(recentPath)}
                      className="w-full flex items-center gap-2 px-3 py-2 rounded-md
                        bg-gray-900 hover:bg-gray-700 text-left transition-colors
                        border border-gray-700"
                    >
                      <Folder className="h-4 w-4 text-gray-400 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-gray-200 truncate">
                          {getWorkspaceBasename(recentPath)}
                        </div>
                        <div className="text-xs text-gray-500 truncate">
                          {shortenWorkspacePath(recentPath)}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button
              variant="ghost"
              onClick={() => setDialogOpen(false)}
              disabled={!workspace}
            >
              Cancel
            </Button>
            <Button
              onClick={() => validateAndOpenWorkspace(pathInput)}
              disabled={validating || !pathInput.trim()}
            >
              {validating ? 'Opening...' : 'Open Workspace'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
