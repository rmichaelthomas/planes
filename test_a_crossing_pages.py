import os
import sys
import tempfile

from scripts.check_pages_surface import check

REPO = os.path.dirname(os.path.abspath(__file__))


def test_surface_checker_follows_cache_busted_modules_and_template_assets():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, "js"))
        with open(os.path.join(root, "index.html"), "w", encoding="utf-8") as fh:
            fh.write('<script type="module" src="./js/stage.mjs?v=director-1"></script>')
        with open(os.path.join(root, "js", "stage.mjs"), "w", encoding="utf-8") as fh:
            fh.write(
                'const scene = `<source srcset="./assets/world.webp">'
                '<image href="./assets/boat.svg#sprite">`;'
            )

        missing = check(root)
        assert {spec for _, spec, _ in missing} == {
            "assets/world.webp",
            "assets/boat.svg",
        }


def test_pages_assembly_derives_the_asset_tree_and_asset_changes_trigger_it():
    with open(os.path.join(REPO, "scripts", "assemble_site.sh"), encoding="utf-8") as fh:
        assembler = fh.read()
    with open(os.path.join(REPO, ".github", "workflows", "pages.yml"), encoding="utf-8") as fh:
        workflow = fh.read()

    assert "find assets -type f" in assembler
    assert '- "assets/**"' in workflow


if __name__ == "__main__":
    fails = []
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_")]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except AssertionError as error:
            print(f"  FAIL  {name}: {error}")
            fails.append(name)
        except Exception as error:  # noqa: BLE001
            print(f"  ERROR {name}: {type(error).__name__}: {error}")
            fails.append(name)
    print(f"\n{len(tests) - len(fails)}/{len(tests)} passing")
    sys.exit(1 if fails else 0)
