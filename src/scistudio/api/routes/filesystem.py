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


def _safe_is_dir(path: str | Path) -> bool:
    """``Path.is_dir()`` that never raises (#1753).

    A path longer than the platform ``PATH_MAX`` (``ENAMETOOLONG``) or an item on
    an offline cloud/network File Provider mount (Box, iCloud — ``ENOTCONN`` /
    ``ETIMEDOUT``) makes ``stat`` raise ``OSError``. Treat any such failure as
    "not a usable directory" so dialog/browse callers degrade instead of 500ing.
    """
    try:
        return Path(path).is_dir()
    except OSError:
        return False


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

    # Route the user-supplied path through the same home/temp allowlist guard
    # the sibling ``stat`` and ``reveal`` endpoints use (#1524). The module
    # docstring mandates the sanitiser for browse too; without it an
    # unauthenticated client could enumerate arbitrary directories
    # (e.g. ``?path=/etc``).
    try:
        target = _resolve_safe_path(path)
        if not target.exists():
            raise HTTPException(status_code=404, detail=f"Path does not exist: {path}")
        if not target.is_dir():
            raise HTTPException(status_code=400, detail=f"Path is not a directory: {path}")
        entries = _list_directory(target)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        # An over-length path (ENAMETOOLONG) or an offline cloud/network mount
        # (ENOTCONN/ETIMEDOUT) makes exists()/is_dir()/iterdir() raise OSError.
        # Return a clean 400 instead of letting it become a 500 (#1753).
        raise HTTPException(
            status_code=400,
            detail=f"Could not read path (too long, offline, or unreadable): {path[:120]}",
        ) from exc
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
    try:
        if not target.exists():
            return FilesystemStatResponse(path=str(target), exists=False)
        kind = "directory" if target.is_dir() else "file"
        size = target.stat().st_size if target.is_file() else None
    except OSError:
        # Over-length (ENAMETOOLONG) or offline cloud/network path: report as
        # not-present rather than raising a 500 (#1753).
        return FilesystemStatResponse(path=str(target), exists=False)
    return FilesystemStatResponse(path=str(target), exists=True, type=kind, size=size)


# ---------------------------------------------------------------------------
# Reveal in native file explorer
# ---------------------------------------------------------------------------


@router.post("/api/filesystem/reveal")
async def reveal_in_explorer(body: RevealRequest) -> dict[str, str]:
    """Open the native file explorer and select/reveal the given path."""
    try:
        target = _resolve_safe_path(body.path)
        exists = target.exists()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        # Over-length or offline path: clean 400 rather than a 500 (#1753).
        raise HTTPException(status_code=400, detail="Path is too long or unreadable") from exc
    if not exists:
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
    prefer_home: bool = Field(
        False,
        description=(
            "When True, open at the last-used location or the user home instead of the "
            "active project root. Used by the create/open-project and diagnostic-export "
            "dialogs, which select a location outside any project."
        ),
    )


class NativeDialogResponse(BaseModel):
    """Response from the native dialog endpoint."""

    paths: list[str] = Field(default_factory=list, description="Selected paths (empty if cancelled)")
    # True when the platform native dialog actually ran (regardless of whether
    # the user picked a path or cancelled). Callers use this to distinguish a
    # user cancel (available=True, paths=[]) from "no native dialog on this
    # platform" (the route raises 500, which clients treat as available=False).
    # This lets the preview export avoid a second (browser) save dialog after a
    # user cancels the native one.
    available: bool = Field(default=True, description="Whether the platform native dialog ran")


# Per-session last-used directory (in-memory, resets on restart).
_last_used_directory: str | None = None


def _resolve_dialog_start_dir(
    initial_dir: str | None,
    prefer_home: bool,
    project_root: str | None,
    last_used: str | None,
) -> str:
    """Choose the directory a native file/directory dialog should open in.

    Project-scope dialogs (the default) prefer the active project root so that
    load/save browsing starts inside the user's project instead of ``$HOME``
    (#1915). Home-scope dialogs (``prefer_home`` — create/open project and the
    diagnostic-bundle export) keep opening at the last-used location or the user
    home, because they select a location *outside* any project.

    ``_safe_is_dir`` swallows ``OSError`` so an over-length or offline candidate
    degrades to the next fallback instead of raising a 500 (#1753).
    """
    if initial_dir and _safe_is_dir(initial_dir):
        return initial_dir
    candidates: list[str | None] = [last_used] if prefer_home else [project_root, last_used]
    for candidate in candidates:
        if candidate and _safe_is_dir(candidate):
            return candidate
    return str(Path.home())


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
    // Create an IShellItem from a filesystem path so the folder dialog can be
    // pointed at a start directory (the project root) via IFileDialog.SetFolder.
    [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
    private static extern void SHCreateItemFromParsingName(
        [MarshalAs(UnmanagedType.LPWStr)] string pszPath,
        IntPtr pbc,
        [In] ref Guid riid,
        [MarshalAs(UnmanagedType.Interface)] out IShellItem ppv);

    public static string Pick(string title, string initialDir, IntPtr owner) {
        var dlg = (IFileDialog)new FileOpenDialogClass();
        uint opts;
        dlg.GetOptions(out opts);
        dlg.SetOptions(opts | 0x20 | 0x40);
        if (title != null) dlg.SetTitle(title);
        if (!string.IsNullOrEmpty(initialDir)) {
            try {
                Guid iidShellItem = new Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE");
                IShellItem folder;
                SHCreateItemFromParsingName(initialDir, IntPtr.Zero, ref iidShellItem, out folder);
                if (folder != null) dlg.SetFolder(folder);
            } catch {
                // Invalid/unreachable start dir -> fall back to the shell default.
            }
        }
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
            + f"$result = [FolderPicker]::Pick('Select Folder', '{safe_initial_dir}', $owner.Handle);"
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
        """Convert an AppleScript alias/file result to a POSIX path."""
        text = hfs.strip()
        for prefix in ("alias ", "file "):
            if text.startswith(prefix):
                text = text[len(prefix) :]
                break
        if text.startswith("POSIX file "):
            text = text[len("POSIX file ") :].strip()
            if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
                text = text[1:-1]
            return text
        if "/" in text and ":" not in text:
            return text
        parts = text.split(":")
        if len(parts) <= 1:
            return text
        posix = "/" + "/".join(parts[1:])
        return posix.rstrip("/") or "/"

    # osascript may return comma-separated aliases for multi-select
    if ", alias " in selected:
        aliases = selected.split(", alias ")
        # First item already has 'alias ' prefix; subsequent ones don't after split
        return [_hfs_to_posix(aliases[0])] + [_hfs_to_posix("alias " + a) for a in aliases[1:]]
    if "|" in selected:
        return [p for p in selected.split("|") if p]
    if selected.startswith(("alias ", "file ", "POSIX file ")):
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
async def native_file_dialog(body: NativeDialogRequest, runtime: RuntimeDep) -> NativeDialogResponse:
    """Open a native OS file or directory dialog and return the selected path.

    Uses platform-specific subprocess calls (PowerShell on Windows, osascript
    on macOS, zenity on Linux). Returns ``{"path": null}`` if the user cancels.
    """
    global _last_used_directory

    # Determine starting directory. Project-scope dialogs default to the active
    # project root; home-scope dialogs (prefer_home) default to last-used/home.
    project_dir = runtime.project_dir
    initial_dir = _resolve_dialog_start_dir(
        body.initial_dir,
        body.prefer_home,
        str(project_dir) if project_dir else None,
        _last_used_directory,
    )

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

    return NativeDialogResponse(paths=selected_paths, available=True)
