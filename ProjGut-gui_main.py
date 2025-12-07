"""
ProjGut GUI Application
=======================

Main Tkinter-based interface for the Project Gutenberg Word Frequency Analyzer.

This application:
- Fetches plain-text eBook files from Project Gutenberg
- Extracts metadata (title, authors)
- Prompts for manual entry of author information
- Parses text to compute word frequencies (excluding stopwords)
- Stores metadata and results in an SQLite database
- Reuses existing stored data when available
- Displays the top 10 most frequent non-stopword words from the selected book

Components
----------
- Tkinter GUI with custom dialogs and themed widgets
- Normalized SQLite schema (book, author, bookAuthors, wordFreqs)
- Text processing utilities (tokenization, stopword filtering)
- Interactive prompts for author entry
- Robust error handling with progress logging

Notes
-----
The system does not yet enforce strict author identity resolution, and
different spellings or formats may create duplicate author records.

Author: Karen R. Christie
CSM CIS 117 Final Project
Date: November–December 2025
"""

import sqlite3
import webbrowser
from tkinter import *
from tkinter.ttk import Combobox, Style
from helpers_text import (
    make_gutenberg_link, fetch_gutenberg_text, extract_title,
    extract_author_block, load_stopwords, MyHTMLParser
)
from helpers_db import (
    DB_PATH, ensure_tables_exist, get_or_create_author,
    lookup_book_and_freqs, load_book_list_from_db
)

# -------------------------------------------
# function that reports progress log messages
# -------------------------------------------
def log_progress(msg):
    """
    Append a status message to the progress log text widget and scroll to the end.

    Parameters
    ----------
    msg : str
        The message to append.
    """
    progress_output.insert(END, msg)
    progress_output.see(END)

# --------------------------------
# GUI helper dialogs (green theme)
# --------------------------------
from tkinter import Toplevel, Label, Entry, Button, StringVar

def _center_window_over_master(dlg, master):
    """
    Center a dialog window (`dlg`) over its parent window (`master`).

    Ensures the dialog appears within the visible bounds of the master window,
    even if the master has been moved or resized.

    Parameters
    ----------
    dlg : tkinter.Toplevel
        The dialog window to position.
    master : tkinter.Widget
        The parent window over which the dialog is centered.
    """
    dlg.update_idletasks()
    mw = master.winfo_width()
    mh = master.winfo_height()
    mx = master.winfo_rootx()
    my = master.winfo_rooty()
    w = dlg.winfo_width()
    h = dlg.winfo_height()
    x = mx + (mw - w) // 2
    y = my + (mh - h) // 2
    dlg.geometry(f"+{max(x,0)}+{max(y,0)}")

class _GreenBaseDialog(Toplevel):
    """
    Base class for modal dialogs using the application's green visual theme.

    Features
    --------
    • Non-resizable `Toplevel` window
    • Standardized background color (#C9F2CE)
    • Title bar text (if provided)
    • ESC/close button handling (returns None)
    • Storage for dialog result via `self.result`
    """

    def __init__(self, master, title):
        super().__init__(master)
        self.transient(master)
        if title:
            self.title(title)
        self.configure(bg="#C9F2CE")
        self.resizable(False, False)
        self.result = None
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _on_cancel(self, *a):
        self.result = None
        self.destroy()

def ask_green_string(master, title, prompt, initial="", allow_empty=False):
    """
    Display a modal green-themed dialog prompting the user for a string.

    Parameters
    ----------
    master : tkinter.Widget
        Parent window.
    title : str
        Title displayed in the dialog's title bar.
    prompt : str
        Instruction text shown above the entry field.
    initial : str, optional
        Initial text to pre-fill in the entry field.
    allow_empty : bool, optional
        If True, empty input is accepted and returned as "".

    Returns
    -------
    str or None
        The user-entered string (stripped of whitespace), or None if canceled.
    """
    # check "or None if cancelled"
    dlg = _GreenBaseDialog(master, title)
    Label(dlg, text=prompt, bg="#C9F2CE", fg="#1F6B2D",
          font=("Arial", 12, "bold")).pack(padx=18, pady=(12,6))
    var = StringVar(value=initial)
    entry = Entry(dlg, textvariable=var, bg="#E9FCDE", fg="#0F4D21", font=("Arial", 12))
    entry.pack(padx=18, pady=(0,10))
    entry.focus_set()

    status = Label(dlg, text="", bg="#C9F2CE", fg="#AA0000", font=("Arial", 10))
    status.pack(padx=18, pady=(0,2))

    def on_ok(event=None):
        val = var.get()
        if not allow_empty:
            if val is None or val.strip() == "":
                status.config(text="Please enter a value or press Cancel.")
                return
            dlg.result = val.strip()
        else:
            # allow empty string but normalize potential whitespace
            dlg.result = val.strip()
        dlg.destroy()

    def on_cancel(event=None):
        dlg.result = None
        dlg.destroy()

    btn_frame = Label(dlg, bg="#C9F2CE")
    btn_frame.pack(pady=(6,12))
    Button(btn_frame, text="OK", bg="#8FFFA0", fg="#0F4D21", width=8, command=on_ok).pack(side="left", padx=6)
    Button(btn_frame, text="Cancel", bg="#F0F0F0", fg="#0F4D21", width=8, command=on_cancel).pack(side="left", padx=6)

    dlg.bind("<Return>", on_ok)
    dlg.bind("<Escape>", on_cancel)

    dlg.grab_set()
    _center_window_over_master(dlg, master)
    dlg.wait_window()
    return dlg.result

def ask_green_integer(master, title, prompt, initial=None, minvalue=None, maxvalue=None):
    """
    Display a modal green-themed dialog prompting the user for an integer.

    Parameters
    ----------
    master : tkinter.Widget
        Parent window.
    title : str
        Dialog title.
    prompt : str
        Prompt text displayed inside the dialog.
    initial : int or None
        Optional integer to pre-populate in the entry box.
    minvalue : int or None
        Optional minimum allowed value.
    maxvalue : int or None
        Optional maximum allowed value.

    Returns
    -------
    int or None
        The validated integer entered by the user, or None if canceled.
    """
    dlg = _GreenBaseDialog(master, title)
    Label(dlg, text=prompt, bg="#C9F2CE", fg="#1F6B2D",
          font=("Arial", 12, "bold")).pack(padx=18, pady=(12,6))
    var = StringVar(value=str(initial) if initial is not None else "")
    entry = Entry(dlg, textvariable=var, bg="#E9FCDE", fg="#0F4D21", font=("Arial", 12))
    entry.pack(padx=18, pady=(0,10))
    entry.focus_set()

    status = Label(dlg, text="", bg="#C9F2CE", fg="#AA0000", font=("Arial", 10))
    status.pack(padx=18, pady=(0,2))

    def on_ok(event=None):
        s = var.get().strip()
        if s == "":
            status.config(text="Please enter an integer.")
            return
        try:
            val = int(s)
        except ValueError:
            status.config(text="Not an integer. Try again.")
            return
        if (minvalue is not None and val < minvalue) or (maxvalue is not None and val > maxvalue):
            status_text = "Value out of range"
            if minvalue is not None and maxvalue is not None:
                status_text += f" ({minvalue}–{maxvalue})"
            elif minvalue is not None:
                status_text += f" (>= {minvalue})"
            elif maxvalue is not None:
                status_text += f" (<= {maxvalue})"
            status.config(text=status_text + ".")
            return
        dlg.result = val
        dlg.destroy()

    def on_cancel(event=None):
        dlg.result = None
        dlg.destroy()

    btn_frame = Label(dlg, bg="#C9F2CE")
    btn_frame.pack(pady=(6,12))
    Button(btn_frame, text="OK", bg="#8FFFA0", fg="#0F4D21", width=8, command=on_ok).pack(side="left", padx=6)
    Button(btn_frame, text="Cancel", bg="#F0F0F0", fg="#0F4D21", width=8, command=on_cancel).pack(side="left", padx=6)

    dlg.bind("<Return>", on_ok)
    dlg.bind("<Escape>", on_cancel)

    dlg.grab_set()
    _center_window_over_master(dlg, master)
    dlg.wait_window()
    return dlg.result

# -----------------------------------------
# GUI main (window & layout initialization)
# -----------------------------------------
window = Tk()
window.title("Parsing with Style with KRC: Project Gutenberg Books - Word Frequency Analyzer")
window.configure(background="#C9F2CE")

# Combobox style (green) + listbox popup colors
style = Style()
style.theme_use("clam")
style.configure(
    "Green.TCombobox",
    arrowsize=18,
    arrowcolor="#1F6B2D",
    foreground="#1F6B2D",
    background="#E9FCDE",
    fieldbackground="#E9FCDE"
)
style.map(
    "Green.TCombobox",
    selectbackground=[("!disabled", "#8FFFA0")],
    selectforeground=[("!disabled", "#0F4D21")]
)
window.option_add("*TCombobox*Listbox.background", "#E9FCDE")
window.option_add("*TCombobox*Listbox.foreground", "#0F4D21")
window.option_add("*TCombobox*Listbox.selectBackground", "#8FFFA0")
window.option_add("*TCombobox*Listbox.selectForeground", "#0F4D21")

# -----------------------------------------
# GUI state variables initialization
# -----------------------------------------
book_choice = None
id_map = {}
gutenberg_id_var = StringVar()

# --------------------------------------------------------
# GUI utilities
# --------------------------------------------------------

# GUI utilities: input helper
def get_requested_gutenberg_id():
    """
    Determine which Project Gutenberg ID the user intends to use.

    Priority
    --------
    1. Manual entry from the text field
    2. Selected book in the dropdown

    Returns
    -------
    tuple
        (gutID, error_message)
        - gutID is an int when valid, otherwise None
        - error_message is None on success, otherwise a descriptive string
    """
    manual = gutenberg_id_var.get().strip()
    if manual:
        cleaned = manual.lower().replace("pg", "")
        try:
            return int(cleaned), None
        except ValueError:
            return None, "Invalid Project Gutenberg book ID (expected a number like 5000)."
    selection = book_choice.get().strip()
    if selection == "__ select a book __" or not selection:
        return None, "Please choose a book or enter a Project Gutenberg book ID."
    gutID = id_map.get(selection)
    if gutID is None:
        return None, "Selection not recognized."
    try:
        return int(str(gutID).lower().replace("pg", "")), None
    except Exception:
        return None, "Invalid Project Gutenberg book ID."

# GUI utilities: linkout function
def open_bio_shelf():
    """
    Open the Project Gutenberg biology bookshelf in the user's default web browser.
    """
    webbrowser.open("https://www.gutenberg.org/ebooks/bookshelf/669")

# GUI utilities: styling of custom widgits
class CustomButton(Button):
    """
    A stylized Tkinter Button with a green on gray theme and effects on clicking the button.

    Includes:
    - Custom fonts and padding
    - Flat style
    - Color transitions on mouse enter/leave
    """
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self.default_bg = "#4B0082"
        self.hover_bg = "#6A0DAD"
        self.fg_color = "#0FBD27"
        self.config(
            bg=self.default_bg,
            fg=self.fg_color,
            activebackground=self.hover_bg,
            activeforeground=self.fg_color,
            relief=FLAT,
            bd=0,
            highlightthickness=0,
            padx=12,
            pady=6,
            font=("Engravers MT", 14, "bold")
        )
        self.bind("<Enter>", self.on_hover)
        self.bind("<Leave>", self.on_leave)

    def on_hover(self, e): self.config(bg=self.hover_bg)
    def on_leave(self, e): self.config(bg=self.default_bg)

# GUI utilities: DB access to provide data to GUI
def refresh_dropdown():
    """
    Reload the book list from the database and repopulate the dropdown widget.

    Side effects
    ------------
    - Updates global variables `dropdown`, `book_choice`, and `id_map`
    - Replaces dropdown values with the latest titles from the database
    - Resets the displayed selection to '__ select a book __'
    """
    global dropdown, book_choice, id_map
    new_book_list, new_id_map = load_book_list_from_db()
    id_map = new_id_map
    dropdown['values'] = new_book_list
    book_choice.set("__ select a book __")

def show_top10_from_db(freq_rows, gutID_int):
    """
    Display the stored top word frequencies for a given Gutenberg book.

    Parameters
    ----------
    freq_rows : iterable of (word, count)
        Rows retrieved from the wordFreqs table.
    gutID_int : int
        Numeric Project Gutenberg ID.

    Side effects
    ------------
    - Clears and rewrites the `words_output` text widget
    - Retrieves book title and all associated authors from the database
    - Displays formatted title, author list, and the top 10 words
    """
    words_output.delete("1.0", END)

    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()

        # Title
        cur.execute("SELECT title FROM book WHERE projGutID=?", (gutID_int,))
        title_row = cur.fetchone()

        # Authors (possibly multiple)
        cur.execute("""
            SELECT a.first, a.last
            FROM bookAuthors ba
            JOIN author a ON ba.author_id = a.id
            WHERE ba.projGutID = ?
            ORDER BY ba.author_order
        """, (gutID_int,))
        authors = cur.fetchall()
        con.close()
    except Exception as e:
        words_output.insert(END, f"(Error fetching author/title: {e})\n\n")
        return

    # Format authors 
    formatted_authors = []
    for first, last in authors:
        if first is None or str(first).strip().lower() in ("", "none", "null"):
            formatted_authors.append(f"{last}")
        else:
            formatted_authors.append(f"{first} {last}")
    author_str = ", ".join(formatted_authors) if formatted_authors else "Unknown Author"

    if title_row:
        display_title = title_row[0].strip()
    else:
        display_title = f"Book {gutID_int}"    # fallback, rare

    words_output.insert(END, f"\n{display_title}\n\nby {author_str}\n\n")

    # Print word frequencies 
    sorted_rows = sorted(freq_rows, key=lambda x: x[1], reverse=True)
    words_output.insert(END, f"  {'Word frequency':>1}  {'Word':<20} \n")
    words_output.insert(END, f"  {'______________':>1}  {'______________':<20} \n")

    for word, count in sorted_rows[:10]:
        words_output.insert(END, f"{count:>16}  {word:<20} \n")

# GUI utilities: reset & cleanup helpers
def clear_fields():
    """
    Reset all user-input fields and clear displayed results/logs.

    Side effects:
    - Resets dropdown
    - Clears the Project Gutenberg book ID entry
    - Clears the progress and output text areas
    """
    book_choice.set("__ select a book __")
    gutenberg_id_var.set("")
    progress_output.delete("1.0", END)
    words_output.delete("1.0", END)

def close_window():
    """
    Close the Tkinter application cleanly without triggering an IDLE warning.
    """
    window.quit()      # Stops the Tkinter mainloop
    window.destroy()   # Closes the window completely

# ---------------------------------
# Main "click" handler (controller)
# ---------------------------------
def click():
    """
    Main controller for the SUBMIT button.

    Workflow
    --------
    1. Determine requested Gutenberg ID (manual entry or dropdown)
    2. Connect to SQLite and ensure required tables exist
    3. Check whether stored frequencies already exist:
        - If yes → display results immediately
    4. If new:
        - Fetch Gutenberg text
        - Extract title and log it
        - Insert book record (if not present)
        - Extract and log the raw author block
        - Ask user for number of authors
        - Collect author names and create/lookup author records
        - Link book ↔ authors in bookAuthors
        - Parse full text using MyHTMLParser
        - Load stopwords
        - Compute complete frequency counts
        - Store top 10 into wordFreqs
    5. Display stored top 10 frequencies
    6. Update dropdown list and clear manual ID entry

    Side effects
    ------------
    Writes progress updates to the `progress_output` widget.
    Writes final results to `words_output`.
    Interacts with the database via helpers and direct SQL.
    """
    # Reset user-visible text areas
    progress_output.delete("1.0", END)
    words_output.delete("1.0", END)

    # Get Gutenberg ID
    gutID_int, err = get_requested_gutenberg_id()
    if err:
        log_progress(err + "\n")
        return

    log_progress(f"Processing Project Gutenberg ID: {gutID_int}\n\n")

    # Connect to the database
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        ensure_tables_exist(con)
        log_progress("Database tables verified or created.\n\n")

    except Exception as e:
        log_progress(f"Database connection error: {e}\n")
        return

    try:
        # Check if book already exists with stored freqs
        book_row, stored_freqs = lookup_book_and_freqs(cur, gutID_int)
        if stored_freqs:
            log_progress(f"📘 Book {gutID_int} found in database — using stored frequencies.\n\n")
            show_top10_from_db(stored_freqs, gutID_int)
            return

        # Fetch Gutenberg text
        url = make_gutenberg_link(gutID_int)
        log_progress(f"Fetching Gutenberg text from:\n{url}\n\n\n")

        text, fetch_err = fetch_gutenberg_text(url)
        if fetch_err:
            log_progress(fetch_err + "\n")
            return

        # Extract Title
        raw_title = extract_title(text)
        book_title = raw_title or "Unknown Title"
        log_progress(f"Detected Title: {book_title}\n\n")

        # Insert book (if new)
        if book_row is None:
            try:
                cur.execute(
                    "INSERT INTO book (projGutID, title) VALUES (?, ?)",
                    (gutID_int, book_title)
                )
                con.commit()
                log_progress(f"Inserted NEW book record:\n  ID={gutID_int}\n  Title='{book_title}'\n\n\n")
            except sqlite3.IntegrityError:
                log_progress(f"Book {gutID_int} already exists — continuing.\n")
            except Exception as e:
                log_progress(f"Error inserting book: {e}\n")
                return

        # Extract Author Block
        author_block = extract_author_block(text)
        log_progress("Extracted Author Block:\n")
        log_progress(f"{author_block}\n\n")

        # Ask user for number of authors
        num_authors = ask_green_integer(
            window,
            "Number of Authors",
            "How many authors does this book have?",
            initial=1,
            minvalue=1
        )
        if not num_authors or num_authors < 1:
            log_progress("ABORTED: At least one author is required.\n")
            return

        log_progress(f"User indicates {num_authors} author(s).\n\n")

        # Collect authors from user & create author records
        author_ids = []
        for i in range(1, num_authors + 1):
            # First name (optional)
            first = ask_green_string(
                window,
                f"Author {i} — First/Middle Names",
                "Enter FIRST & MIDDLE names (optional):\nEnter 'none' for single-name authors.",
                allow_empty=True
            )
            if first is None:
                log_progress("Author entry cancelled by user.\n")
                return
            first = first.strip()
            if first == "" or first.lower() == "none":
                first = None  # stored as NULL

            # Last name (required)
            last = ask_green_string(
                window,
                f"Author {i} — Last Name",
                "Enter LAST name:\n(For single-name authors, enter the name here.)"
            )
            if last is None:
                log_progress("Author entry cancelled by user.\n")
                return
            last = last.strip()
            if last == "":
                log_progress(f"ABORTED: Last name for Author {i} cannot be blank.\n")
                return

            author_id = get_or_create_author(cur, first, last)
            author_ids.append(author_id)
            log_progress(f"Author {i} recorded: {first or ''} {last} (id={author_id})\n")

        log_progress("\nAll author records complete.\n\n\n")

        # Insert relationships into bookAuthors
        try:
            for order, a_id in enumerate(author_ids, start=1):
                cur.execute(
                    """
                    INSERT OR IGNORE INTO bookAuthors (projGutID, author_id, author_order)
                    VALUES (?, ?, ?)
                    """,
                    (gutID_int, a_id, order)
                )
                log_progress(f"Linked Book {gutID_int} → Author {a_id} (order = {order})\n")
            con.commit()
            log_progress("\nAuthor linkage completed.\n\n\n")
        except Exception as e:
            log_progress(f"Error linking book and authors: {e}\n")
            return

        refresh_dropdown()
        gutenberg_id_var.set("")

        # Parse text & load stopwords
        parser = MyHTMLParser()
        parser.feed(text.lower())
        log_progress("Text parsed. Extracted word tokens from Project Gutenberg source.\n\n")

        stopwords = load_stopwords()
        log_progress(f"Loaded {len(stopwords)} stopwords.\n\n")

        full_counts = parser.frequency(5, stopwords=stopwords, top_k=None)
        if not full_counts:
            log_progress("No valid tokens found after filtering.\n")
            return

        # Store Top 10 frequencies
        try:
            sorted_rows = sorted(full_counts.items(), key=lambda x: x[1], reverse=True)
            top10 = sorted_rows[:10]

            log_progress("Storing Top 10 word frequencies...\n")
            for word, count in top10:
                cur.execute(
                    "INSERT OR REPLACE INTO wordFreqs (projGutID, word, word_count) VALUES (?, ?, ?)",
                    (gutID_int, word, count)
                )
                log_progress(f"  {word:<15} → {count}\n")

            con.commit()

        except Exception as e:
            log_progress(f"Error saving word frequencies: {e}\n")
            return

        # Display results
        _, freq_rows = lookup_book_and_freqs(cur, gutID_int)

        show_top10_from_db(freq_rows, gutID_int)

    finally:
        con.close()

# ---------------------------
# Build UI (layout)
# ---------------------------

# Small header (row 0)
Label(window,
      text="Project Gutenberg Biology Shelf - Top 10 Interesting Words in   ",
      bg="#C9F2CE", fg="#1F6B2D",
      font="noteworthy 15 bold").grid(row=0, column=0, sticky=W, padx=(10,0), pady=(5,0))

# Large header (row 1)
Label(window,
      text="Biological Texts of Interest & Historical Significance  ",
      bg="#C9F2CE", fg="#1F6B2D",
      font="Zapfino 30 bold").grid(row=1, column=0, sticky=W, padx=(10,0), pady=(1,0))

# Dropdown label (row 2)
Label(window,
      text="  Choose a book in the database:",
      bg="#C9F2CE", fg="#1F6B2D",
      font="noteworthy 20 bold").grid(row=2, column=0, sticky=W, padx=(2,0), pady=(0,2))

# Dropdown combobox with placeholder (row 3)
## Load book list from DB to populate dropdown
book_list, id_map = load_book_list_from_db()

## format dropdown
book_choice = StringVar(value="__ select a book __")
dropdown = Combobox(window,
                    textvariable=book_choice,
                    values=book_list,
                    width=140,
                    font=("Arial", 12),
                    style="Green.TCombobox")
dropdown.grid(row=3, column=0, sticky=W, padx=(20,0))

# Label OR (row 4)
Label(window,
      text="OR",
      bg="#C9F2CE", fg="#1F6B2D",
      font="noteworthy 30 bold").grid(row=4, column=0, sticky=W)

# Label for manual Project Gutenberg book ID entry box (row 5)
Label(window,
      text="  Add a new book! Enter the Project Gutenberg book ID (e.g. pg5000 or 5000):",
      bg="#C9F2CE", fg="#1F6B2D",
      font="noteworthy 20 bold").grid(row=5, column=0, sticky=W)

# Box for manual Project Gutenberg book ID entry (row 5)
gutenberg_id_entry = Entry(window, textvariable=gutenberg_id_var, width=10, bg='#E9FCDE', font=("Arial", 12))
gutenberg_id_entry.bind("<Return>", lambda event: click())
gutenberg_id_entry.grid(row=5, column=0, sticky=E, padx=(0,260), pady=(6,0))

# Linkout to Project Gutenberg biology shelf(row 6)
bio_link = Label(window,
                 text="Browse the Project Gutenberg biology shelf for ideas",
                 fg="#00CC44",
                 cursor="hand2",
                 bg="#C9F2CE",
                 font=("Arial", 16, "underline"))
bio_link.grid(row=6, column=0, pady=(20,0))   # Centered
bio_link.bind("<Button-1>", lambda e: open_bio_shelf())

# Buttons for SUBMIT & CLEAR (row 7)
CustomButton(window, text="SUBMIT", width=6, command=click).grid(row=7, column=0, sticky=W, padx=(10,0), pady=(0,0))
CustomButton(window, text="CLEAR", width=6, command=clear_fields).grid(row=7, column=0, sticky=E, padx=(0,10), pady=(0,0))

# Progress log output label and text areas (rows 8-9)
Label(window,
      text="Progress Log:",
      bg="#C9F2CE", fg="#1F6B2D",
      font="noteworthy 20 bold").grid(row=8, column=0, sticky=W, padx=(10,0))

progress_output = Text(window, width=145, height=30, wrap=WORD, background="#F7F7F7")
progress_output.grid(row=9, column=0, sticky=W, padx=(10,0))

# Divider (row 10)
divider = Frame(window, bg="#C9F2CE")
divider.grid(row=10, column=0, pady=10)
Label(divider, text="_____________________________________________________________", 
      bg="#C9F2CE", fg="#1F6B2D",
      font=("noteworthy", 18, "bold")
).pack(fill="x")

# Top words output label and text area (rows 11 & 12)
Label(window,
      text="  Top 10 Interesting Words Found in Book:",
      bg="#C9F2CE", fg="#1F6B2D",
      font="noteworthy 20 bold").grid(row=11, column=0, sticky=W)
words_output = Text(window, width=145, height=20, wrap=WORD, background="#F7F7F7")
words_output.grid(row=12, column=0, columnspan=2, sticky=W, padx=(10,0))

# EXIT button (rows 13 & 14)
Label(window,
      text="Click to Exit:",
      bg="#C9F2CE", fg="#1F6B2D",
      font="noteworthy 20 bold").grid(row=13, column=0, sticky=W, padx=(10,0))
CustomButton(window, text="EXIT", width=6, command=close_window).grid(row=14, column=0, sticky=W, padx=(10,0), pady=(5,0))

# Blank row (row 15)
divider = Frame(window, bg="#C9F2CE")
divider.grid(row=15, column=0, sticky="we", pady=5)
Label(divider, text="   ", bg="#C9F2CE", fg="#1F6B2D", font=("noteworthy", 18, "bold")).pack(fill="x")

if __name__ == "__main__":
    window.mainloop()
