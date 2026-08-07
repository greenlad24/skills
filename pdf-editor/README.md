# Local PDF Editor

A small PDF editor that runs entirely on your own Mac. Open a PDF, type on it,
sign it, tick boxes, cover things up, and save a new copy.

Nothing is uploaded anywhere. The app makes **no network requests at all** —
the two libraries it uses (pdf.js for viewing, pdf-lib for writing) are stored
in `vendor/` next to it. You can unplug the network and it works exactly the
same.

Built to run on macOS Big Sur (11.7) with the Safari or Chrome that ships with
it — no installation, no Homebrew, no Node.

## Getting started

1. Put this `pdf-editor` folder wherever you like — Documents, the Desktop,
   anywhere.
2. Double-click **`Open PDF Editor.command`**.
   A Terminal window opens and your browser opens the editor. Leave the
   Terminal window open while you work; closing it shuts the editor down.
3. Drag a PDF onto the window, or click **Open PDF…**.

The first time you run it, macOS may say the file is from an unidentified
developer. Right-click `Open PDF Editor.command` → **Open** → **Open**, and
it won't ask again. If it refuses to run at all, open Terminal and run:

```
chmod +x "/path/to/pdf-editor/Open PDF Editor.command"
xattr -dr com.apple.quarantine "/path/to/pdf-editor"
```

You can also just double-click `index.html` to open it directly in your
browser. That works too — it is only a little slower on large documents,
which is why the launcher exists.

### What the launcher actually does

It starts a tiny web server on `127.0.0.1` (this machine only, not reachable
from your network) using Ruby, Python or PHP — whichever your Mac already has.
Browsers restrict what a page loaded from a bare `file://` URL may do, and the
local server sidesteps that. Nothing is sent anywhere; the server only hands
your browser the files sitting in this folder.

## Using it

Pick a tool, then click on the page.

| Tool | What it does |
| --- | --- |
| **Select** | Click anything you have added to move it, resize it or change it. |
| **Text** | Click where the text should sit — the click point is the baseline, so click straight on a form's line. Type; Return starts a new line. |
| **Signature** | Draw one with the trackpad, type one in a handwriting font, or use a photo/scan of your real signature. Then click the page to place it. |
| **Image** | Place any PNG or JPEG — initials, a stamp, a logo. |
| **Check** | A tick mark for checkboxes. |
| **Whiteout** | Drag out a white rectangle to cover up existing content before typing over it. |

Then click **Save PDF**. The edited copy lands in your Downloads folder as
`<original name>-signed.pdf`. **Your original file is never modified.**

### Signatures

The **Upload** tab is the one to use if you want your real signature: sign a
blank sheet of paper in black pen, photograph it with your phone, and pick the
photo. "Remove white background" knocks out the paper so only the ink is
placed on the PDF.

Signatures you make are remembered on this Mac (in the browser's local storage,
never sent anywhere) so you can reuse them next time. Untick **Remember on
this Mac** if you would rather not, or remove saved ones with the ✕ on each.

### Shortcuts

| Key | Action |
| --- | --- |
| `V` `T` `S` `I` `C` `B` | Select, Text, Signature, Image, Check, Box |
| `⌘S` | Save |
| `⌘Z` | Undo |
| `Delete` | Remove the selected item |
| Arrow keys | Nudge the selected item (hold `Shift` for bigger steps) |
| `Esc` | Deselect / finish editing text |

### Flatten form fields

If your PDF has fillable form fields, tick **Flatten form fields** before
saving. Their current values get baked into the page so nobody can change
them afterwards. Leave it unticked to keep the form fillable.

## Notes and limits

- **Password-protected PDFs** can't be opened. Open the file in Preview first,
  then File → Export as PDF without a password.
- Typed text is written as real, selectable PDF text in Helvetica, Times or
  Courier. If you type a character those fonts can't represent (emoji, unusual
  accents, curly quotes pasted from elsewhere), that text box is written as a
  crisp image instead so nothing is lost or mangled.
- Typed signatures are always written as images — PDF's built-in fonts have
  nothing handwriting-like, and the handwriting fonts used here are the ones
  already on your Mac.
- The editor draws on top of the page. It does not delete or rewrite existing
  content — that is what the Whiteout tool is for.

## What's in the folder

```
index.html                 the app
app.js                     all of the logic
styles.css                 styling
vendor/pdf.min.js          pdf.js — renders the pages (Mozilla, Apache 2.0)
vendor/pdf.worker.min.js
vendor/pdf-lib.min.js      pdf-lib — writes the new PDF (MIT)
Open PDF Editor.command    double-click launcher
```
