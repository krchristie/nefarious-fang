"""
helpers_db
==========

Database helper functions for the Project Gutenberg word-frequency application.

This module provides all interactions with the SQLite backend, including:

- Ensuring the database schema exists
- Creating or reusing author records
- Retrieving stored book metadata and word-frequency results
- Preparing a formatted list of books for GUI display

The database schema includes:

- ``author``: individual authors
- ``book``: Project Gutenberg books
- ``bookAuthors``: junction table linking books ↔ authors (supports multi-author texts)
- ``wordFreqs``: stored top word-frequency results per book

Public API
----------

.. autofunction:: ensure_tables_exist
.. autofunction:: get_or_create_author
.. autofunction:: lookup_book_and_freqs
.. autofunction:: load_book_list_from_db

Notes
-----
This module performs no GUI operations and no logging; callers are responsible
for user-visible reporting. All functions assume a valid SQLite connection or
cursor is provided.

Author: Karen R. Christie
CSM CIS 117 Final Project
Date: November–December 2025
"""


import sqlite3

DB_PATH = "ProjGutBooks.db"


def ensure_tables_exist(con):
    """
    Create all required SQLite tables if they do not already exist.

    Notes
    -----
    • Safe to call repeatedly.
    • No logging is performed; caller is responsible for any reporting.
    • Schema reflects a normalized design where:
        - author: stores authors
        - book: stores books
        - bookAuthors: junction table linking books ↔ authors
        - wordFreqs: word frequency table linked to book
    """
    cur = con.cursor()

    # author table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS author (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first TEXT,
            last TEXT
        )
    """)

    # book table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS book (
            projGutID INTEGER PRIMARY KEY,
            title TEXT
        )
    """)

    # bookAuthors linking table 
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bookAuthors (
            projGutID INTEGER,
            author_id INTEGER,
            author_order INT,
            PRIMARY KEY (projGutID, author_id),
            FOREIGN KEY (projGutID) REFERENCES book(projGutID),
            FOREIGN KEY (author_id) REFERENCES author(id)
        )
    """)

    # wordFreqs 
    cur.execute("""
        CREATE TABLE IF NOT EXISTS wordFreqs (
            projGutID INTEGER,
            word TEXT,
            word_count INTEGER,
            PRIMARY KEY (projGutID, word),
            FOREIGN KEY (projGutID) REFERENCES book(projGutID)
        )
    """)

    con.commit()


def get_or_create_author(cur, first, last):
    """
    Retrieve an existing author or insert a new one.

    Parameters
    ----------
    cur : sqlite3.Cursor
        Database cursor.
    first : str or None
        First/middle name(s), or None for mononym authors.
    last : str
        Last name (required).

    Returns
    -------
    int
        The author’s database ID.

    Notes
    -----
    - Matching is strict: both `first` and `last` must match.
    """
    cur.execute(
        "SELECT id FROM author WHERE first = ? AND last = ?",
        (first, last)
    )
    row = cur.fetchone()
    if row:
        return row[0]

    cur.execute(
        "INSERT INTO author (first, last) VALUES (?, ?)",
        (first, last)
    )
    return cur.lastrowid


def lookup_book_and_freqs(cur, gutID_int):
    """
    Look up a book and any stored word frequencies.

    Parameters
    ----------
    cur : sqlite3.Cursor
        The database cursor.
    gutID_int : int
        Project Gutenberg numeric identifier.

    Returns
    -------
    tuple
        (book_row, freq_rows)
        - book_row is (projGutID, title) or None if the book is not stored.
        - freq_rows is a list of (word, count) tuples, or None if no frequencies exist.
    """
    cur.execute(
        "SELECT projGutID, title FROM book WHERE projGutID=?",
        (gutID_int,)
    )
    book = cur.fetchone()

    cur.execute(
        "SELECT word, word_count FROM wordFreqs WHERE projGutID=?",
        (gutID_int,)
    )
    freqs = cur.fetchall()

    return book, freqs if freqs else None


def load_book_list_from_db():
    """
    Load a cleaned and formatted list of books for use in the GUI dropdown.

    Returns
    -------
    (list[str], dict[str, int])
        display_list :
            A list of display labels of the form:
                "Cleaned Title (Lastname)"           -- single author
                "Cleaned Title (Lastname et al.)"    -- multiple authors
                "Cleaned Title (Unknown Author)"     -- no author data

            Titles have leading articles ("A ", "An ", "The ") removed
            for sorting and display purposes only.

        idmap :
            A dictionary mapping each display label → projGutID.

    Notes
    -----
    - Ensures the database schema exists before reading.
    - Author information is determined by querying bookAuthors and author.
    - The first author's last name determines the label suffix.
    - The original title is stored unchanged in the database;
        only the *display* version is altered for the dropdown.
    """

    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()

        ensure_tables_exist(con)

        # Load all books
        cur.execute("SELECT projGutID, title FROM book ORDER BY title;")
        rows = cur.fetchall()

    except Exception:
        return [], {}
    finally:
        try:
            con.close()
        except:
            pass

    display = []
    idmap = {}

    for bid, title in rows:

        # Get ordered list of authors
        try:
            con = sqlite3.connect(DB_PATH)
            cur = con.cursor()
            cur.execute("""
                SELECT a.first, a.last
                FROM bookAuthors ba
                JOIN author a ON ba.author_id = a.id
                WHERE ba.projGutID = ?
                ORDER BY ba.author_order ASC
            """, (bid,))
            authors = cur.fetchall()
            con.close()
        except Exception:
            authors = []

        # Determine label suffix:
        if not authors:
            suffix = "Unknown Author"
        else:
            first_author_last = authors[0][1].strip()
            if len(authors) == 1:
                suffix = first_author_last
            else:
                suffix = f"{first_author_last} et al."

        # Strip leading articles from titles for dropdown display
        clean_title = title.strip()
        low = clean_title.lower()
        for art in ("a ", "an ", "the "):
            if low.startswith(art):
                clean_title = clean_title[len(art):]
                break

        # Build final label
        label = f"{clean_title} ({suffix})"

        display.append(label)
        idmap[label] = bid

    return display, idmap


