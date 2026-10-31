# Release checklist

PomoPet currently ships an unsigned Windows installer. Complete this checklist
from a clean `main` branch before publishing a GitHub Release.

## Prepare

1. Select the version and update it in `package.json`, `frontend/package.json`,
   `frontend/package-lock.json`, and `CHANGELOG.md`.
2. Confirm the changelog date and release notes.
3. Decide whether the release is public, prerelease, or draft.
4. Confirm that the release continues to comply with the repository's MIT License.

## Verify locally

```powershell
npm test
npm --prefix frontend run lint
conda run -n pomopet --cwd backend python -m unittest discover -s tests
npm run dist
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/smoke-backend.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/smoke-packaged-app.ps1
```

The expected installer is written to `dist/`. Test it on a clean Windows 10 or
Windows 11 machine, including first launch, provider setup, a focus session,
application restart, and uninstall behavior.

## Build on GitHub

Run the **Build Windows release** workflow manually, or push a matching semantic
version tag such as `v0.1.0`. A tag build fails when the tag does not match both
package versions. Download the workflow artifact and verify `SHA256SUMS.txt`.

## Publish manually

1. Create an annotated tag from the verified commit and push that exact tag.
2. Open GitHub Releases and create a draft for the tag.
3. Use the matching section from `CHANGELOG.md` as the release notes.
4. Attach the installer and `SHA256SUMS.txt` from the successful workflow run.
5. Mark the release as a prerelease if it is not ready for general use.
6. Publish only after the clean-machine smoke test passes.
