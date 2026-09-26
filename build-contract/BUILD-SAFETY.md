# Build Safety Contract

1. Build only on Windows x64.
2. Use a lock file and reuse `.venv` when its lock hash matches.
3. Treat native process exit code—not stderr text—as success/failure.
4. Assert the entry script and assets before invoking PyInstaller.
5. Test manifest XML with `mt.exe` or omit the custom manifest and use PyInstaller defaults.
6. Smoke-test source, frozen EXE, bridge child process and installed application.
7. Never copy the launcher EXE without `_internal`.
8. Ship one Inno Setup installer containing the entire one-folder output.
