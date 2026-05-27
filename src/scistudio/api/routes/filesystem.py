"""Filesystem browsing and reveal endpoints for the project tree and universal file picker."""

from __future__ import annotations

import os
import platform
import string
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from scistudio.api.deps import get_runtime
from scistudio.api.runtime import ApiRuntime

router = APIRouter(tags=["filesystem"])
RuntimeDep = Annotated[ApiRuntime, Depends(get_runtime)]


# ---------------------------------------------------------------------------
# Path sanitiser (CodeQL py/path-injection guard).
#
# Both the reveal and browse endpoints take a user-supplied path that flows
# directly into filesystem operations (``Path.exists``, ``Path.iterdir``)
# and into a native shell command (``explorer.exe`` / ``open`` / ``xdg-open``).
# Without a sanitiser, a malicious client could ask the server to inspect
# or open arbitrary filesystem locations (``/etc/shadow``, ``C:\\Windows``,
# ...). Restrict accepted paths to the user's home tree and the system temp
# tree — the two places SciStudio projects and pytest fixtures actually live.
#
# Implementation note: CodeQL ``py/path-injection`` recognises
# ``os.path.realpath`` + ``os.path.commonpath`` as the canonical sanitiser
# pattern, but does NOT recognise ``pathlib.Path.is_relative_to``. The two
# are functionally equivalent; we use the form CodeQL accepts.
# ---------------------------------------------------------------------------


_SAFE_PATH_ALLOWED_ROOTS: tuple[str, ...] = (
    os.path.realpath(os.path.expanduser("~")),
    os.path.realpath(tempfile.gettempdir()),
)


def _resolve_safe_path(user_path: str | Path) -> Path:
    """Resolve *user_path* and require it to live under an allowed root.

    Raises
    ------
    ValueError
        If the canonicalised path does not fall under any allowed root.
        Callers translate this to HTTP 400.
    """
    candidate = os.path.realpath(os.fspath(user_path))
    for root in _SAFE_PATH_ALLOWED_ROOTS:
        try:
            if os.path.commonpath([root, candidate]) == root:
                return Path(candidate)
        except ValueError:
            # commonpath raises ValueError when paths are on different
            # drives (Windows) or when one is absolute and one relative.
            continue
    raise ValueError(f"path must be under user home or system temp; got {candidate}")


# ---------------------------------------------------------------------------
# Shared models
# ---------------------------------------------------------------------------


class TreeEntry(BaseModel):
    """A single file or directory entry in a project tree listing."""

    name: str
    type: str  # "file" or "directory"
    size: int | None = None


class TreeResponse(BaseModel):
    """Response body for a single-level directory listing."""

    entries: list[TreeEntry] = Field(default_factory=list)


class RevealRequest(BaseModel):
    """Request body for the filesystem reveal action."""

    path: str


class FilesystemEntry(BaseModel):
    """A single entry in a filesystem browse listing."""

    name: str
    type: str  # "file" | "directory"
    size: int | None = None


class FilesystemBrowseResponse(BaseModel):
    """Response from the filesystem browse endpoint."""

    path: str
    entries: list[FilesystemEntry]


class FilesystemStatResponse(BaseModel):
    """Response from the filesystem stat endpoint."""

    path: str
    exists: bool
    type: str | None = None
    size: int | None = None


# ---------------------------------------------------------------------------
# Project tree endpoint (scoped to project root)
# ---------------------------------------------------------------------------


@router.get(
    "/api/projects/{project_id}/tree",
    response_model=TreeResponse,
)
async def project_tree(
    project_id: str,
    runtime: RuntimeDep,
    path: str = Query("", description="Relative path within the project root"),
) -> TreeResponse:
    """Return one level of directory listing for a project (lazy loading).

    Directories are listed first, then files, both sorted alphabetically.
    Path traversal via ``..`` is rejected.
    """
    # Resolve project root
    project = runtime.known_projects.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    project_root = Path(project.path).resolve()

    # Security: reject path traversal
    if ".." in path.split("/") or ".." in path.split("\\"):
        raise HTTPException(status_code=400, detail="Path traversal is not allowed")

    target = (project_root / path).resolve()
    # Ensure target is within project root
    try:
        target.relative_to(project_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Path is outside project root") from exc

    if not target.is_dir():
        raise HTTPException(status_code=404, detail="Directory not found")

    dirs: list[TreeEntry] = []
    files: list[TreeEntry] = []
    try:
        for child in target.iterdir():
            # Skip hidden files/directories
            if child.name.startswith("."):
                continue
            if child.is_dir():
                dirs.append(TreeEntry(name=child.name, type="directory"))
            elif child.is_file():
                try:
                    size = child.stat().st_size
                except OSError:
                    size = None
                files.append(TreeEntry(name=child.name, type="file", size=size))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Permission denied") from exc

    dirs.sort(key=lambda e: e.name.lower())
    files.sort(key=lambda e: e.name.lower())
    return TreeResponse(entries=dirs + files)


# ---------------------------------------------------------------------------
# Universal filesystem browse endpoint (NOT project-scoped)
# ---------------------------------------------------------------------------


def _is_hidden(name: str) -> bool:
    """Return ``True`` for dot-prefixed names on non-Windows platforms."""
    if platform.system() == "Windows":
        return False
    return name.startswith(".")


def _list_roots() -> list[FilesystemEntry]:
    """Return filesystem roots (drive letters on Windows, ``/`` on Unix)."""
    if platform.system() == "Windows":
        entries: list[FilesystemEntry] = []
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.isdir(drive):
                entries.append(FilesystemEntry(name=drive, type="directory"))
        return entries
    return [FilesystemEntry(name="/", type="directory")]


def _list_directory(directory: Path) -> list[FilesystemEntry]:
    """Return one level of *directory* contents (dirs first, alpha)."""
    dirs: list[FilesystemEntry] = []
    files: list[FilesystemEntry] = []

    try:
        children = sorted(directory.iterdir(), key=lambda p: p.name.lower())
    except PermissionError:
        return []

    for child in children:
        if _is_hidden(child.name):
            continue
        try:
            if child.is_dir():
                dirs.append(FilesystemEntry(name=child.name, type="directory"))
            else:
                try:
                    size = child.stat().st_size
                except OSError:
                    size = None
                files.append(FilesystemEntry(name=child.name, type="file", size=size))
        except (PermissionError, OSError):
            continue

    return dirs + files


@router.get("/api/filesystem/browse", response_model=FilesystemBrowseResponse)
async def browse_filesystem(
    path: str = Query("", description="Directory path to list. Empty string returns filesystem roots."),
) -> FilesystemBrowseResponse:
    """Return one level of directory listing at *path*.

    If *path* is empty, returns the filesystem roots (drive letters on
    Windows; ``/`` on Linux/macOS).
    """
    if not path:
        return FilesystemBrowseResponse(path="", entries=_list_roots())

    target = Path(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path does not exist: {path}")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {path}")

    entries = _list_directory(target)
    return FilesystemBrowseResponse(path=str(target), entries=entries)


@router.get("/api/filesystem/stat", response_model=FilesystemStatResponse)
async def stat_filesystem(
    path: str = Query(..., description="File or directory path to inspect."),
) -> FilesystemStatResponse:
    """Return existence and coarse type information for a safe path."""

    try:
        target = _resolve_safe_path(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not target.exists():
        return FilesystemStatResponse(path=str(target), exists=False)
    kind = "directory" if target.is_dir() else "file"
    size: int | None = None
    if target.is_file():
        try:
            size = target.stat().st_size
        except OSError:
            size = None
    return FilesystemStatResponse(path=str(target), exists=True, type=kind, size=size)


# ---------------------------------------------------------------------------
# Reveal in native file explorer
# ---------------------------------------------------------------------------


@router.post("/api/filesystem/reveal")
async def reveal_in_explorer(body: RevealRequest) -> dict[str, str]:
    """Open the native file explorer and select/reveal the given path."""
    try:
        target = _resolve_safe_path(body.path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path does not exist")

    system = platform.system()
    try:
        if system == "Windows":
            subprocess.Popen(["explorer", "/select,", str(target)])
        elif system == "Darwin":
            subprocess.Popen(["open", "-R", str(target)])
        else:
            # Linux/other: open the parent directory
            parent = str(target.parent) if target.is_file() else str(target)
            subprocess.Popen(["xdg-open", parent])
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail="Could not find the file explorer command for this platform",
        ) from exc

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Native OS file/directory dialog
# ---------------------------------------------------------------------------


class NativeDialogRequest(BaseModel):
    """Request body for the native file/directory dialog."""

    mode: str = Field(
        ..., pattern="^(file|directory|save_file)$", description="Dialog type: 'file', 'directory', or 'save_file'"
    )
    initial_dir: str | None = Field(None, description="Optional starting directory for the dialog")
    default_filename: str | None = Field(None, description="Default filename for save_file mode")
    file_filter: str | None = Field(None, description="File type filter description (e.g. 'YAML files (*.yaml)')")


class NativeDialogResponse(BaseModel):
    """Response from the native dialog endpoint."""

    paths: list[str] = Field(default_factory=list, description="Selected paths (empty if cancelled)")


# Per-session last-used directory (in-memory, resets on restart).
_last_used_directory: str | None = None


def _ps_single_quote_escape(value: str) -> str:
    """Escape ``'`` for embedding inside a PowerShell single-quoted string.

    PowerShell literal-quotes a single quote inside ``'...'`` by doubling
    it (``''``). Workflow names like ``Bob's run`` would otherwise break
    the dialog script syntax (#617).
    """

    return value.replace("'", "''")


def _native_dialog_windows(
    mode: str,
    initial_dir: str | None,
    default_filename: str | None = None,
    file_filter: str | None = None,
) -> list[str]:
    """Open a native Windows file/directory dialog via PowerShell.

    Returns a list of selected paths (empty list if cancelled).
    For directory mode the list contains at most one element.
    For file mode the list may contain multiple files.
    For save_file mode the list contains at most one element.
    """
    # Escape ``'`` -> ``''`` in any user-controllable value before
    # interpolating into PowerShell single-quoted strings (#617).
    safe_initial_dir = _ps_single_quote_escape(initial_dir or "")
    safe_default_filename = _ps_single_quote_escape(default_filename or "")
    safe_file_filter = _ps_single_quote_escape(file_filter or "YAML files (*.yaml)|*.yaml|All files (*.*)|*.*")
    owner_form_setup = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "[System.Windows.Forms.Application]::EnableVisualStyles();"
        "$owner = New-Object System.Windows.Forms.Form;"
        "$owner.StartPosition = 'CenterScreen';"
        "$owner.Width = 1;"
        "$owner.Height = 1;"
        "$owner.Opacity = 0;"
        "$owner.ShowInTaskbar = $false;"
        "$owner.TopMost = $true;"
        "$owner.Show();"
        "$owner.Activate();"
    )
    owner_form_teardown = "if ($owner) { $owner.Close(); $owner.Dispose(); }"
    if mode == "directory":
        # Use modern IFileOpenDialog COM with FOS_PICKFOLDERS for Vista+ style
        # instead of the legacy Win2000-era FolderBrowserDialog.
        # The C# source is compiled once per session by PowerShell Add-Type;
        # the static FolderPicker.Pick() method shows the dialog and returns
        # the selected path (or null on cancel).
        # NOTE: COM interface method stubs follow vtable order — do NOT
        # reorder or remove entries.
        cs_source = r"""
using System;
using System.Runtime.InteropServices;

[ComImport, Guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7"), ClassInterface(ClassInterfaceType.None)]
public class FileOpenDialogClass { }

[ComImport, Guid("42F85136-DB7E-439C-85F1-E4075D135FC8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IFileDialog {
    [PreserveSig] int Show(IntPtr hwnd);
    void SetFileTypes();
    void SetFileTypeIndex();
    void GetFileTypeIndex();
    void Advise();
    void Unadvise();
    void SetOptions(uint fos);
    void GetOptions(out uint pfos);
    void SetDefaultFolder();
    void SetFolder(IShellItem psi);
    void GetFolder();
    void GetCurrentSelection();
    void SetFileName();
    void GetFileName();
    void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string pszTitle);
    void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string pszText);
    void SetFileNameLabel();
    void GetResult(out IShellItem ppsi);
    void AddPlace();
    void SetDefaultExtension();
    void Close();
    void SetClientGuid();
    void ClearClientData();
    void SetFilter();
}

[ComImport, Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IShellItem {
    void BindToHandler();
    void GetParent();
    void GetDisplayName(uint sigdnName, [MarshalAs(UnmanagedType.LPWStr)] out string ppszName);
    void GetAttributes();
    void Compare();
}

public static class FolderPicker {
    public static string Pick(string title, IntPtr owner) {
        var dlg = (IFileDialog)new FileOpenDialogClass();
        uint opts;
        dlg.GetOptions(out opts);
        dlg.SetOptions(opts | 0x20 | 0x40);
        if (title != null) dlg.SetTitle(title);
        int hr = dlg.Show(owner);
        if (hr != 0) return null;
        IShellItem item;
        dlg.GetResult(out item);
        string path;
        item.GetDisplayName(0x80058000, out path);
        return path;
    }
}
"""
        # Pass C# source in a PowerShell single-quoted string (escape ' as '').
        ps_script = (
            owner_form_setup
            + "Add-Type -TypeDefinition '"
            + cs_source.replace("'", "''")
            + "';"
            + "try {"
            + "$result = [FolderPicker]::Pick('Select Folder', $owner.Handle);"
            + "if ($result) { $result } else { '' }"
            + "} finally {"
            + owner_form_teardown
            + "}"
        )
    elif mode == "save_file":
        ps_script = (
            owner_form_setup
            + "$d = New-Object System.Windows.Forms.SaveFileDialog;"
            + f"$d.InitialDirectory = '{safe_initial_dir}';"
            + f"$d.FileName = '{safe_default_filename}';"
            + f"$d.Filter = '{safe_file_filter}';"
            + "try {"
            + "if ($d.ShowDialog($owner) -eq 'OK') { $d.FileName } else { '' }"
            + "} finally {"
            + owner_form_teardown
            + "}"
        )
    else:
        # Bug 1 fix: single braces for non-f-string lines.
        # Bug 2 fix: enable Multiselect and return pipe-separated FileNames.
        ps_script = (
            owner_form_setup
            + "$d = New-Object System.Windows.Forms.OpenFileDialog;"
            + "$d.Multiselect = $true;"
            + f"$d.InitialDirectory = '{safe_initial_dir}';"
            + "try {"
            + "if ($d.ShowDialog($owner) -eq 'OK') { ($d.FileNames -join '|') } else { '' }"
            + "} finally {"
            + owner_form_teardown
            + "}"
        )
    # No timeout: this is a desktop-local server and the user may legitimately
    # spend an arbitrary amount of time browsing the dialog (#678).
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
        capture_output=True,
        text=True,
        timeout=None,
    )
    selected = result.stdout.strip()
    if not selected:
        return []
    # File mode returns pipe-separated paths; directory mode returns a single path.
    return [p for p in selected.split("|") if p]


def _native_dialog_macos(
    mode: str,
    initial_dir: str | None,
    default_filename: str | None = None,
    file_filter: str | None = None,
) -> list[str]:
    """Open a native macOS file/directory dialog via osascript.

    Returns a list of selected paths (empty list if cancelled).
    """
    if mode == "directory":
        if initial_dir:
            script = f'choose folder with prompt "Select Directory" default location POSIX file "{initial_dir}"'
        else:
            script = 'choose folder with prompt "Select Directory"'
    elif mode == "save_file":
        name_part = f' default name "{default_filename}"' if default_filename else ""
        loc_part = f' default location POSIX file "{initial_dir}"' if initial_dir else ""
        script = f'choose file name with prompt "Save As"{name_part}{loc_part}'
    else:
        if initial_dir:
            script = (
                f'choose file with prompt "Select File" default location POSIX file "{initial_dir}"'
                " with multiple selections allowed"
            )
        else:
            script = 'choose file with prompt "Select File" with multiple selections allowed'
    # No timeout: this is a desktop-local server and the user may legitimately
    # spend an arbitrary amount of time browsing the dialog (#678).
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=None,
    )
    selected = result.stdout.strip()
    if not selected:
        return []

    def _hfs_to_posix(hfs: str) -> str:
        """Convert an HFS alias string to a POSIX path."""
        text = hfs.strip()
        if text.startswith("alias "):
            text = text[len("alias ") :]
        parts = text.split(":")
        posix = "/" + "/".join(parts[1:])
        return posix.rstrip("/") or "/"

    # osascript may return comma-separated aliases for multi-select
    if ", alias " in selected:
        aliases = selected.split(", alias ")
        # First item already has 'alias ' prefix; subsequent ones don't after split
        return [_hfs_to_posix(aliases[0])] + [_hfs_to_posix("alias " + a) for a in aliases[1:]]
    if selected.startswith("alias "):
        return [_hfs_to_posix(selected)]
    return [selected]


def _native_dialog_linux(
    mode: str,
    initial_dir: str | None,
    default_filename: str | None = None,
    file_filter: str | None = None,
) -> list[str]:
    """Open a native Linux file/directory dialog via zenity.

    Returns a list of selected paths (empty list if cancelled).
    """
    cmd = ["zenity", "--file-selection"]
    if mode == "directory":
        cmd.append("--directory")
    elif mode == "save_file":
        cmd.append("--save")
        cmd.append("--confirm-overwrite")
        if default_filename:
            cmd.extend(["--filename", default_filename])
    else:
        cmd.append("--multiple")
        cmd.extend(["--separator", "|"])
    if initial_dir:
        cmd.extend(["--filename", initial_dir + "/"])
    # No timeout: this is a desktop-local server and the user may legitimately
    # spend an arbitrary amount of time browsing the dialog (#678).
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=None)
    selected = result.stdout.strip()
    if not selected:
        return []
    return [p for p in selected.split("|") if p]


@router.post("/api/filesystem/native-dialog", response_model=NativeDialogResponse)
async def native_file_dialog(body: NativeDialogRequest) -> NativeDialogResponse:
    """Open a native OS file or directory dialog and return the selected path.

    Uses platform-specific subprocess calls (PowerShell on Windows, osascript
    on macOS, zenity on Linux). Returns ``{"path": null}`` if the user cancels.
    """
    global _last_used_directory

    # Determine starting directory: request param > last-used > home
    initial_dir = body.initial_dir
    if not initial_dir or not Path(initial_dir).is_dir():
        initial_dir = _last_used_directory
    if not initial_dir or not Path(initial_dir).is_dir():
        initial_dir = str(Path.home())

    system = platform.system()
    try:
        if system == "Windows":
            selected_paths = _native_dialog_windows(
                body.mode,
                initial_dir,
                body.default_filename,
                body.file_filter,
            )
        elif system == "Darwin":
            selected_paths = _native_dialog_macos(
                body.mode,
                initial_dir,
                body.default_filename,
                body.file_filter,
            )
        else:
            selected_paths = _native_dialog_linux(
                body.mode,
                initial_dir,
                body.default_filename,
                body.file_filter,
            )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Native dialog command not available on this platform ({system})",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            status_code=504,
            detail="Dialog timed out (user may have left the dialog open)",
        ) from exc

    # Track last-used directory for the session
    if selected_paths:
        first = selected_paths[0]
        parent = str(Path(first).parent) if Path(first).is_file() else first
        _last_used_directory = parent

    return NativeDialogResponse(paths=selected_paths)
