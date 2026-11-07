## What changed

<!-- One paragraph. What is the user-visible behavior before and after? -->

## Why

<!-- Link the issue or describe the user journey this fixes. -->

## Checks

- [ ] `python3 -m compileall src` passes
- [ ] `pytest -q` passes
- [ ] `bash -n install.sh uninstall.sh` passes
- [ ] `msgfmt --check po/*.po` passes
- [ ] No hardcoded UI string; `.pot` and `po/vi.po` updated if strings changed
- [ ] New async path takes a `Gio.Cancellable` and is cancelled on file change
- [ ] New viewer implements `get_desired_size`, `teardown` and declares input limits
- [ ] D-Bus signatures in `src/integrations/nautilus.py` still match Nautilus
- [ ] Manual matrix: Wayland and X11, light and dark, `en` and `vi`
- [ ] Keyboard path: `Space`, arrows, `Esc`, `Ctrl+F`, `F`/`F11`, `O`, `P`, `F2`, `Del`
- [ ] Screenshots attached for visual changes

## Risk

<!-- What could break? Which viewer, platform or file type is most exposed? -->
