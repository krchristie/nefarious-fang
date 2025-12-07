"""
helpers_db
==========

Database access layer for the Project Gutenberg word-frequency application.

This module centralizes all interaction with the SQLite backend. It provides
helpers for creating and validating the database schema, inserting and
retrieving book and author records, managing book–author relationships, storing
computed word-frequency results, and producing cleaned labels for GUI display.
All operations here are side-effect free with respect to the GUI and contain
no printing or logging.

Available functions
-------------------
- :func:`ensure_tables_exist`  
    Create all required tables if they do not already exist.

- :func:`insert_book`  
    Insert a book record unless it is already present.

- :func:`get_or_create_author`  
    Look up an author by name or insert a new one if absent.

- :func:`lookup_book_and_freqs`  
    Retrieve a book record and any stored word-frequency results.

- :func:`insert_book_author_links`  
    Add ordered entries linking a book to one or more authors.

- :func:`get_book_title`  
    Return the stored title for a specific Project Gutenberg ID.

- :func:`get_book_authors`  
    Retrieve an ordered list of authors linked to a book.

- :func:`store_word_frequencies`  
    Store (or update) the top word-frequency results for a book.

- :func:`load_book_list_from_db`  
    Construct a cleaned display list of books and build a mapping suitable
    for GUI dropdowns.

Notes
-----
- This module performs **no GUI actions and no logging**. All user-visible
  reporting must be performed by the caller.
- All functions assume a valid SQLite connection or cursor is provided.
- Schema is designed for normalized representation of books, authors, and
  many-to-many author relationships.

Author: Karen R. Christie
CSM CIS 117 Final Project
Date: November–December 2025
"""

import sqlite3

DB_PATH = "ProjGutBooks.db"


def ensure_tables_exist(con):
    """
    Create the full SQLite schema if it does not already exist.

    Parameters
    ----------
    con : sqlite3.Connection
        Active database connection.

    Notes
    -----
    This function is safe to call repeatedly. It silently ensures all required
    tables exist but performs no logging. The schema contains:

    - ``author``: stores author names  
    - ``book``: stores Project Gutenberg books  
    - ``bookAuthors``: junction table linking books ↔ authors  
    - ``wordFreqs``: stored top word-frequency results  
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


def insert_book(cur, gutID_int, title):
    """
    Insert a book record if it does not already exist.

    Parameters
    ----------
    cur : sqlite3.Cursor
        Active database cursor.
    gutID_int : int
        Project Gutenberg numeric identifier.
    title : str
        Title of the book.

    Notes
    -----
    The insert uses ``INSERT OR IGNORE`` so existing records are preserved.
    """
    cur.execute(
        "INSERT OR IGNORE INTO book (projGutID, title) VALUES (?, ?)",
        (gutID_int, title)
    )


def get_or_create_author(cur, first, last):
    """
    Retrieve an existing author record or create a new one.

    Parameters
    ----------
    cur : sqlite3.Cursor
        Active database cursor.
    first : str or None
        First or middle name(s). ``None`` indicates a mononym author.
    last : str
        Last name or full mononym name.

    Returns
    -------
    int
        The author’s database ID.

    Notes
    -----
    Matching is exact on both ``first`` and ``last``.
    If no match exists, a new row is inserted.
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
    Retrieve stored metadata and word-frequency results for a book.

    Parameters
    ----------
    cur : sqlite3.Cursor
        Active database cursor.
    gutID_int : int
        Project Gutenberg numeric identifier.

    Returns
    -------
    tuple
        ``(book_row, freq_rows)``  
        - ``book_row`` is ``(projGutID, title)`` or ``None`` if the book is absent.  
        - ``freq_rows`` is a list of ``(word, count)`` pairs, or ``None`` if no
          frequency data is stored.
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

    return book, (freqs if freqs else None)


def insert_book_author_links(cur, gutID_int, author_ids):
    """
    Create ordered links between a book and its authors.

    Parameters
    ----------
    cur : sqlite3.Cursor
        Active database cursor.
    gutID_int : int
        Project Gutenberg numeric identifier.
    author_ids : list of int
        Author IDs in the correct author order for the book.

    Notes
    -----
    ``INSERT OR IGNORE`` prevents accidental duplicate associations.
    """
    for order, a_id in enumerate(author_ids, start=1):
        cur.execute(
            """
            INSERT OR IGNORE INTO bookAuthors (projGutID, author_id, author_order)
            VALUES (?, ?, ?)
            """,
            (gutID_int, a_id, order)
        )


def get_book_title(cur, gutID_int):
    """
    Retrieve the stored title of a book.

    Parameters
    ----------
    cur : sqlite3.Cursor
        Active database cursor.
    gutID_int : int
        Project Gutenberg numeric identifier.

    Returns
    -------
    str or None
        The title if present, otherwise ``None``.
    """
    cur.execute(
        "SELECT title FROM book WHERE projGutID=?",
        (gutID_int,)
    )
    row = cur.fetchone()
    return row[0] if row else None


def get_book_authors(cur, gutID_int):
    """
    Retrieve the ordered list of authors for a given book.

    Parameters
    ----------
    cur : sqlite3.Cursor
        Active database cursor.
    gutID_int : int
        Project Gutenberg numeric identifier.

    Returns
    -------
    list of (str or None, str)
        A list of ``(first, last)`` tuples in author order.
    """
    cur.execute("""
        SELECT a.first, a.last
        FROM bookAuthors ba
        JOIN author a ON ba.author_id = a.id
        WHERE ba.projGutID = ?
        ORDER BY ba.author_order
    """, (gutID_int,))
    return cur.fetchall()


def store_word_frequencies(cur, gutID_int, top10):
    """
    Store the top word-frequency results for a book.

    Parameters
    ----------
    cur : sqlite3.Cursor
        Active database cursor.
    gutID_int : int
        Project Gutenberg numeric identifier.
    top10 : list of (str, int)
        List of ``(word, count)`` pairs representing the top results.

    Notes
    -----
    ``INSERT OR REPLACE`` ensures updates overwrite older values.
    """
    for word, count in top10:
        cur.execute(
            """
            INSERT OR REPLACE INTO wordFreqs (projGutID, word, word_count)
            VALUES (?, ?, ?)
            """,
            (gutID_int, word, count)
        )


def load_book_list_from_db():
    """
    Construct a cleaned list of book display labels for use in the GUI.

    Returns
    -------
    tuple
        ``(display_list, idmap)``  
        - ``display_list`` : list of strings formatted as  
          ``"Cleaned Title (Lastname)"`` for one author,  
          ``"Cleaned Title (Lastname et al.)"`` for multiple authors,  
          or ``"Cleaned Title (Unknown Author)"`` when no author data exists.  
        - ``idmap`` : dict mapping each display label → ``projGutID``.

    Notes
    -----
    - Ensures the database schema exists before reading.
    - Removes leading articles (“A”, “An”, “The”) *for display only*.
    - Determines the first author's last name for label formatting.
    """
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()

        ensure_tables_exist(con)

        cur.execute("SELECT projGutID, title FROM book ORDER BY title;")
        rows = cur.fetchall()

    except Exception:
        return [], {}
    finally:
        try:
            con.close()
        except Exception:
            pass

    display = []
    idmap = {}

    for bid, title in rows:
        # Fetch authors for each book
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

        # Determine suffix for label
        if not authors:
            suffix = "Unknown Author"
        else:
            last = authors[0][1].strip()
            suffix = last if len(authors) == 1 else f"{last} et al."

        # Remove leading articles for display
        clean_title = title.strip()
        low = clean_title.lower()
        for art in ("a ", "an ", "the "):
            if low.startswith(art):
                clean_title = clean_title[len(art):]
                break

        label = f"{clean_title} ({suffix})"
        display.append(label)
        idmap[label] = bid

    return display, idmap
