<!-- generated-by: openapi_reference -->
# Server API

## /api/ai/pty/internal/notify
- POST:  Internal Notify

## /api/ai/pty/internal/request-tab
- POST:  Internal Request Tab

## /api/ai/status
- GET: Provider Status

## /api/blocks/
- GET: List Blocks

## /api/blocks/template
- GET: Get Block Template

## /api/blocks/validate-connection
- POST: Validate Connection Route

## /api/blocks/{block_type}/schema
- GET: Get Block Schema

## /api/data/upload
- POST: Upload Data

## /api/data/{data_ref}
- GET: Get Data Metadata

## /api/data/{data_ref}/preview
- GET: Preview Data

## /api/filesystem/browse
- GET: Browse Filesystem

## /api/filesystem/native-dialog
- POST: Native File Dialog

## /api/filesystem/reveal
- POST: Reveal In Explorer

## /api/git/branch/create
- POST: Branch Create

## /api/git/branch/switch
- POST: Branch Switch

## /api/git/branches
- GET: Branches

## /api/git/branches/{name}
- DELETE: Branch Delete

## /api/git/cherry-pick
- POST: Cherry Pick

## /api/git/commit
- POST: Commit

## /api/git/diff
- GET: Diff

## /api/git/log
- GET: Log

## /api/git/merge
- POST: Merge

## /api/git/merge/abort
- POST: Merge Abort

## /api/git/merge/complete
- POST: Merge Complete

## /api/git/merge/stage-file
- POST: Merge Stage File

## /api/git/restore
- POST: Restore

## /api/git/stash
- GET: Stash List

## /api/git/stash/apply
- POST: Stash Apply

## /api/git/stash/save
- POST: Stash Save

## /api/git/stash/{stash_id}
- DELETE: Stash Drop

## /api/git/status
- GET: Status Endpoint

## /api/lint/python
- POST: Lint Python

## /api/logs/stream
- GET: Logs Stream

## /api/projects/
- GET: List Projects
- POST: Create Project

## /api/projects/{project_id}
- DELETE: Delete Project
- GET: Get Project
- PUT: Update Project

## /api/projects/{project_id}/file
- GET: Read Project File
- PUT: Write Project File

## /api/projects/{project_id}/tree
- GET: Project Tree

## /api/runs
- GET: List Runs

## /api/runs/_health
- GET: Runs Health

## /api/runs/{run_id}
- GET: Get Run

## /api/runs/{run_id}/methods
- GET: Get Run Methods

## /api/runs/{run_id}/rerun
- POST: Rerun Run

## /api/workflows/
- POST: Create Workflow

## /api/workflows/export-path
- POST: Export Workflow To Path

## /api/workflows/import
- POST: Import Workflow

## /api/workflows/import-path
- POST: Import Workflow From Path

## /api/workflows/list
- GET: List Workflows

## /api/workflows/{workflow_id}
- DELETE: Delete Workflow
- GET: Get Workflow
- PUT: Update Workflow

## /api/workflows/{workflow_id}/blocks/{block_id}/cancel
- POST: Cancel Block

## /api/workflows/{workflow_id}/cancel
- POST: Cancel Workflow

## /api/workflows/{workflow_id}/execute
- POST: Execute Workflow

## /api/workflows/{workflow_id}/execute-from
- POST: Execute From Workflow

## /api/workflows/{workflow_id}/pause
- POST: Pause Workflow

## /api/workflows/{workflow_id}/resume
- POST: Resume Workflow
