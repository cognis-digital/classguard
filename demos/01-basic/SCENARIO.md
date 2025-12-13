# Demo 01 - Basic marking compliance check

This demo runs CLASSGUARD against two sample documents shipped in this folder:

* `good_memo.txt` - a correctly marked CONFIDENTIAL memo. Top and bottom
  banners match, every content paragraph carries a portion marking, and the
  highest portion `(C)` equals the banner.
* `bad_memo.txt` - a defective memo: the bottom banner is missing, one
  paragraph is portion-marked `(S)` which **exceeds** the `CONFIDENTIAL`
  banner, and another paragraph has no portion marking at all.

## Run it

```sh
# Compliant document -> exit 0
python -m classguard check demos/01-basic/good_memo.txt

# Defective document -> exit 1, errors listed
python -m classguard check demos/01-basic/bad_memo.txt

# Machine-readable output for pipelines / dashboards
python -m classguard check demos/01-basic/bad_memo.txt --format json
```

## What to look for

For `bad_memo.txt` you should see findings including:

* `BANNER_BOTTOM_MISSING` (error) - no closing banner.
* `PORTION_EXCEEDS_BANNER` (error) - an `(S)` portion under a `CONFIDENTIAL` banner.
* `PORTION_UNMARKED` (warn) - a paragraph with no portion marking.

The `good_memo.txt` run reports `COMPLIANT` and exits `0`.

## Scope

CLASSGUARD only inspects marking **text** for structural consistency. It does
not assign classification levels, judge whether content *should* be classified,
or perform any action beyond reporting. It is a compliance/QA aid for cleared
work.
