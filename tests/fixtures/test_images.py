"""End-to-end test image path constants.

Per ``docs/specs/phase11-implementation-standards.md`` §Q6, the four
example images live at ``C:\\Users\\jiazh\\Desktop\\workspace\\Example\\images``.
Filenames contain spaces and parentheses; the raw string keeps Windows
backslashes intact. Centralising the paths means a single test-image
directory move only requires one file edit.

E2E tests import the constants instead of hardcoding paths. If the
``TEST_IMAGES_DIR`` does not exist (CI environment without the test
images), tests that depend on these fixtures should skip via
``pytest.skip("test images unavailable", allow_module_level=True)``
at the top of the test module after a path-existence check.
"""

from pathlib import Path

TEST_IMAGES_DIR = Path(r"C:\Users\<user>\Desktop\workspace\Example\images")

K562_L_2845_TIF = TEST_IMAGES_DIR / "K562_L_2845 (uV).tif"
K562_L_SPECTRA_TIF = TEST_IMAGES_DIR / "K562_L_spectra (uV).tif"
K562_UL_2845_TIF = TEST_IMAGES_DIR / "K562_UL_2845 (uV).tif"
K562_UL_SPECTRA_TIF = TEST_IMAGES_DIR / "K562_UL_spectra (uV).tif"

SEGMENTATION_IMAGES = [K562_L_2845_TIF, K562_UL_2845_TIF]
SPECTRA_IMAGES = [K562_L_SPECTRA_TIF, K562_UL_SPECTRA_TIF]
