#!/usr/bin/env python
# -*- coding: utf-8 -*-

from bs4 import BeautifulSoup
import bs4
import requests
import sys
import os
import json
import stat
import inspect
from random import randint
import glob

# This enables us to display unicode characters correctly
import locale
locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

def dbg_printf(format, *args):
    """
    C-Style function that writes debugging output to the terminal. If debug flag is off
    this function does not print anything

    :param format: The format string
    :param args: Arguments
    :return: None
    """
    global debug_flag

    # Do not print anything annoying
    if debug_flag is False:
        return

    frame = inspect.currentframe()
    prev_frame = frame.f_back
    code = prev_frame.f_code
    prev_name = code.co_name

    # Make it more human readable by replacing the name with
    # an easy to understand one
    if prev_name == "<module>":
        prev_name = "[Top Level Module]"
    else:
        prev_name += "()"

    # Write the prologue of debugging information
    sys.stderr.write("%-28s: " % (prev_name,))

    format = format % tuple(args)
    sys.stderr.write(format)

    # So we do not need to worry about new lines
    sys.stderr.write('\n')

    return

def get_webpage(word):
    """
    This function returns a string which is the webpage of a given word
    Returns None if the return code is not HTTP status 200 which means an error
    happened
    
    :return: str/None 
    """
    url = "http://dict.youdao.com/search?le=eng&q=%s&keyfrom=dict2.index" % (word, )
    r = requests.get(url)
    if r.status_code != 200:
        dbg_printf("Error executing HTTP request to %s; return code %d",
                   url,
                   r.status_code)

        return None

    return r.text

def parse_webpage(s):
    """
    Given the text of the webpage, parse it as an instance of a beautiful soup,
    using the default parser and encoding
    
    :param s: The text of the webpage 
    :return: beautiful soup object
    """
    return BeautifulSoup(s, 'html.parser')

def get_collins_dict(tree):
    """
    This function returns results by collins dictionary, given the beautiful soup
    tree object
    
    The return value is defined as follows: 
      
    {
      "word": "The word"
      "phonetic": "The pronunciation"
      "frequency": 4,    // This is always a number between 1 and 5, or -1 to indicate unknown
      "meanings": [
        {
          "category": "n. v. adj. adv. , etc.",
          "text": "Meaning of the word",
          "examples": [
            {
              "text": "Text of the example, with <b></b> being the keyword"
              "translation": "Translation of the text"
            },
          ]
        }, ...
      ],
      "word-group": [
        {
          "text": "Word group text",
          "meaning": "The meaning of the word group"
        }, ...
      ],
    }
    
    :param tree: The beautiful soup tree
    :return: A list of the dict as specified as above, or None if fails
    """
    collins_result = tree.find(id="collinsResult")
    if isinstance(collins_result, bs4.element.Tag) is False:
        dbg_printf("Did not find id='collinsResult'")
        # it is not a valid div object (usually None if the tag does
        # not exist)
        return None
    elif collins_result.name != "div":
        dbg_printf("id='collinsResult' is not a div tag")
        # It is a valid tag, but the name is not div
        # This should be strange, though
        return None

    # This list contains all meanings of the word, each with a pronunciation
    top_level_list = collins_result.select("div.wt-container")
    ret_list = []
    # We set this to be the first word
    actual_key = None
    # This is the index for <div>.wt
    wt_index = -1
    for sub_tree in top_level_list:
        wt_index += 1
        # We append this into a list
        ret = {}

        # This <h4> contains the main word, the pronunciation
        h4 = sub_tree.find("h4")
        if h4 is None:
            dbg_printf("Did not find <h4> (wt_index = %d)", wt_index)
            return None

        span_list = h4.find_all("span")
        if len(span_list) < 1:
            dbg_printf("Did not find <span> under <h4> (wt_index = %d)", wt_index)
            return None

        # This is the word we are looking for
        ret["word"] = span_list[0].text

        # This contains the phonetic
        em = h4.find("em")
        if em is None:
            # If we did not find <em> then there is no pronunciation
            # and we just set it as empty string
            ret["phonetic"] = ""
        else:
            # Save the phonetic (note: this is not ASCII)
            ret["phonetic"] = em.text

        # Initialize the meanings list
        ret["meanings"] = []

        # Get the frequency span; If no such element just set it to -1
        # which means the freq is invalid
        freq_span = h4.select("span.star")
        if len(freq_span) == 0:
            ret["frequency"] = -1
        else:
            freq = -1
            star_attr = freq_span[0].attrs["class"]
            if "star1" in star_attr:
                freq = 1
            elif "star2" in star_attr:
                freq = 2
            elif "star3" in star_attr:
                freq = 3
            elif "star4" in star_attr:
                freq = 4
            elif "star5" in star_attr:
                freq = 5

            ret["frequency"] = freq

        # This is all meanings
        li_list = sub_tree.find_all("li")
        li_count = -1
        for li in li_list:
            li_count += 1

            # Just add stuff into this dict object
            d = {}

            # find main div and example div list
            main_div_list = li.select("div.collinsMajorTrans")
            if len(main_div_list) == 0:
                continue
            else:
                main_div = main_div_list[0]

            example_div_list = li.select("div.exampleLists")

            # Then find the <p> in the first div, which contains word category and
            # the meaning of the word
            p = main_div.find("p")
            if p is None:
                dbg_printf("Did not find the <p> under main <div> (index = %d)",
                           li_count)
                return None

            span = p.find("span")
            # This is possible if this entry is simply a redirection
            if span is None:
                # if there is an <a> in the <span> then it is a redirection
                a = p.find("a")
                if a is not None:
                    # Make it invisible
                    d["category"] = "REDIRECTION"
                else:
                    d["category"] = "UNKNOWN"

                meaning = ""
                for content in p.contents:
                    if isinstance(content, bs4.element.Tag) is True:
                        if content.name == "a":
                            meaning += ("<green>" + " ".join(content.text.split()) + "</green>")
                        elif content.name == "b":
                            meaning += ("<red>" + " ".join(content.text.split()) + "</red>")
                        else:
                            meaning += " ".join(content.text.split())
                    else:
                        meaning += " ".join(content.split())

                    meaning += " "

                d["text"] = meaning
                d["examples"] = []

                ret["meanings"].append(d)

                continue

            # Save the category as category attribute
            d["category"] = span.text
            # Then for all text and child nodes in p, find the span
            # and then add all strings together after it
            meaning = ""
            for content in p.contents:
                if isinstance(content, bs4.element.Tag) is True and \
                   content.name == "span" and \
                   content.text == span.text:
                    continue

                # for keywords in the article we manually surround them with
                # <b></b> tags
                if isinstance(content, bs4.element.Tag) is True and \
                   content.name == "b":
                    content = "<red>" + " ".join(content.text.split()) + "</red>"
                elif isinstance(content, bs4.element.Tag):
                    content = " ".join(content.text.split())
                else:
                    content = " ".join(content.split())

                if len(content) == 0:
                    continue

                # Then use space to separate the contents
                meaning += (content + " ")

            # If we did not find anything then return
            if len(meaning) == 0:
                dbg_printf("Did not find the meaning of the word in the <p> under main div (index = %d)",
                           li_count)
                return None

            # Save the meaning of the word as the text
            d["text"] = meaning

            # Push examples into this list
            l = []
            d["examples"] = l
            # These are all examples
            for div in example_div_list:
                # Text is the first p and translation is the second p
                # We do not care the remaining <p>, but if there are less than
                # two then we simply return
                p_list = div.find_all("p")
                if len(p_list) < 2:
                    return None

                l.append({
                    "text": p_list[0].text.strip(),
                    "translation": p_list[1].text.strip(),
                })

            # Append the dict here such that if we continue before here
            # the changes will not be committed
            ret["meanings"].append(d)

        #
        # Then start to extract word groups
        #

        word_group_list = []
        ret["word-group"] = word_group_list

        word_group_div_list = tree.select("#wordGroup")
        if len(word_group_div_list) == 0:
            dbg_printf("Did not find word group; return empty word group")
        else:
            word_group_div = word_group_div_list[0]
            # This is a list of <p> tags that contains the word group
            word_group_p_list = word_group_div.select("p.wordGroup")
            word_group_index = -1
            for word_group_p in word_group_p_list:
                word_group_index += 1
                # Search for the <a> tag that contains the text of the word group
                a_list = word_group_p.select("a.search-js")
                if len(a_list) == 0:
                    dbg_printf("Did not find word group text (index = %d)",
                               word_group_index)
                    continue

                text = a_list[0].text
                meaning = ""
                for content in word_group_p.contents:
                    if isinstance(content, bs4.element.Tag) is True:
                       continue

                    meaning += (" ".join(content.split()) + " ")

                meaning = meaning.strip()
                if len(meaning) == 0:
                    dbg_printf("Did not find word group meaning (index = %d)",
                               word_group_index)
                    continue

                # Finally add an element into the word group list
                word_group_list.append(
                    {"text": text,
                     "meaning": meaning}
                )

        # Set the actual key on the web page
        if actual_key is None:
            actual_key = ret["word"]

        ret_list.append(ret)

    # Last check to avoid adding a None key into the cache
    if actual_key is None:
        dbg_printf("Did not find actual key")
        return None

    # Add the word to the cache
    add_to_cache(actual_key, ret_list)

    return ret_list

def get_cache_file_list(path):
    """
    This function counts the number of json files under a given directory.
    To save an system call the path is given as the argument
    
    If the passed path is not a valid directory then the result is undefined
    
    :return: int, as the number of json files 
    """
    return glob.glob(os.path.join(path, "*.json"))

# The name of the directory under the file directory as the word cache
CACHE_DIRECTORY = "cache"

# The max number of entries we allow for the cache
# When we add to the cache we check this first, and if the actual number of
# json files is greater than this we randomly delete files from the cache
# If this is set to -1 then there is no limit
# If this is set to 0 then cache is disabled
CACHE_MAX_ENTRY = 10

def trim_cache(cache_dir, limit):
    """
    Randomly remove cache content under given path until the number of file equals
    or is less than the given limit
    
    :param cache_dir: Under which we store cached file
    :param limit: The maximum number of entries allowed for the cache
    :return: int, the number of files we actually deleted
    """
    cache_file_list = get_cache_file_list(cache_dir)
    current_cache_size = len(cache_file_list)

    deleted_count = 0
    if current_cache_size >= limit:
        # This is the number of files we need to delete
        delta = current_cache_size - limit
        # Then do a permutation of the list and pick the first
        # "deleted_count" elements to delete
        for i in range(0, delta):
            exchange_index = randint(0, current_cache_size - 1)
            # Then exchange the elements
            t = cache_file_list[exchange_index]
            cache_file_list[exchange_index] = cache_file_list[i]
            cache_file_list[i] = t

        for i in range(0, delta):
            try:
                os.unlink(cache_file_list[i])
            except OSError:
                # Offset the += 1 later
                deleted_count -= 1
            deleted_count += 1

    return deleted_count

def add_to_cache(word, d):
    """
    This function adds a word and its associated dictionary object into the local cache
    If this word is queried in the future, it will be served from the cache
    
    If the word is already in the cache we just ignore it
    
    :param word: The word queried 
    :param d: The dictionary object returned by the parser
    :return: None
    """
    # If cache is disabled then return directly
    if CACHE_MAX_ENTRY == 0:
        return

    # Also take care of this
    if no_add_flag is True:
        dbg_printf("no_add_flag is on; do not add to cache")
        return

    # This is the directory of the current file
    file_dir = get_file_dir()
    cache_dir = os.path.join(file_dir, CACHE_DIRECTORY)

    # If the cache directory has not yet been created then just create it
    if os.path.isdir(cache_dir) is False:
        os.mkdir(cache_dir)

    # Then before we check for the existence of the file, we
    # check whether the cache directory is full, and if it is
    # randomly choose one and then remove it
    # -1 means there is no limit
    if CACHE_MAX_ENTRY != -1:
        # Since we will add a new entry after this, so the actual limit
        # is 1 less than the defined constant
        ret = trim_cache(cache_dir, CACHE_MAX_ENTRY - 1)
        if ret > 0:
            dbg_printf("Deleted %d file(s) from the cache", ret)

    # This is the word file
    word_file = os.path.join(cache_dir, "%s.json" % (word, ))
    # If the file exists then warning
    if os.path.isfile(word_file) is True:
        dbg_printf("Overwriting cache file for word: %s", word)

    fp = open(word_file, "w")
    json.dump(d, fp)
    fp.close()

    return

def check_in_cache(word):
    """
    Check whether a word exists in the cache, and if it does then we load from the cache
    directly and then display. If not in the cache return None
    
    :param word: The word to be queried
    :return: dict/None
    """
    # This is the directory of the current file
    file_dir = get_file_dir()
    cache_dir = os.path.join(file_dir, CACHE_DIRECTORY)

    # If the cache directory has not yet been created then just create it
    if os.path.isdir(cache_dir) is False:
        dbg_printf("Cache directory not valid: %s", cache_dir)
        return None

    # This is the word file
    word_file = os.path.join(cache_dir, "%s.json" % (word, ))
    # If the file exists then ignore it
    if os.path.isfile(word_file) is False:
        dbg_printf("File %s is not valid cached word file", word_file)
        return None

    fp = open(word_file, "r")
    # If we could not decode the json object just remove the invalid
    # file and return None
    try:
        d = json.load(fp)
    except ValueError:
        print("Invalid JSON object: remove %s" % (word_file, ))
        os.unlink(word_file)
        fp.close()
        return None

    fp.close()

    return d

RED_TEXT_START = "\033[1;31m"
RED_TEXT_END = "\033[0m"
GREEN_TEXT_START = "\033[1;32m"
GREEN_TEXT_END = "\033[0m"
YELLOW_TEXT_START = "\033[1;33m"
YELLOW_TEXT_END = "\033[0m"

def print_red(text, output_device):
    """
    Prints the given text in read fore color
    
    :param text: The text to be printed
    :param output_device: Object that supports write() method
    :return: None
    """
    output_device.write(RED_TEXT_START)
    output_device.write(text)
    output_device.write(RED_TEXT_END)
    return

def print_yellow(text, output_device):
    """
    Prints the text in yellow foreground color
    
    :param text: The text to be printed 
    :param output_device: Object that supports write() method
    :return: None
    """
    output_device.write(YELLOW_TEXT_START)
    output_device.write(text)
    output_device.write(YELLOW_TEXT_END)
    return

def process_color(s):
    """
    Replace color marks in a string with actual color control characters defined
    by the terminal
    
    :param s: The input string
    :return: str
    """
    s = s.replace("<red>", RED_TEXT_START)
    s = s.replace("</red>", RED_TEXT_END)
    s = s.replace("<green>", GREEN_TEXT_START)
    s = s.replace("</green>", GREEN_TEXT_END)

    return s

def collins_pretty_print(dict_list, output_device=sys.stdout):
    """
    Prints a dict object in pretty form. The input dict object may
    be None, in which case we skip printing
    
    :param dict_list: A list of dict objects returned from the parser
    :param output_device: An output object that supports write() method
                          for printing or aggregating values
    :return: None
    """
    global verbose_flag
    global m5_flag

    if dict_list is None:
        return

    for d in dict_list:
        print_red(d["word"], output_device)
        output_device.write("        ")

        # Write the frequency if it has one
        freq = d["frequency"]
        if freq != -1:
            output_device.write("[%s]        " % ("*" * freq, ))

        output_device.write(d["phonetic"])
        output_device.write("\n")

        counter = 1
        for meaning in d["meanings"]:
            if m5_flag is True and counter == 6:
                return

            output_device.write("%d. (%s) " % (counter, meaning["category"]))
            counter += 1

            text = process_color(meaning["text"])
            output_device.write(text)

            output_device.write("\n")

            if verbose_flag is True:
                for example in meaning["examples"]:
                    output_device.write("    - ")
                    output_device.write(example["text"])
                    output_device.write("\n")
                    output_device.write("      ")
                    output_device.write(example["translation"])
                    output_device.write("\n")

        # If we also print word group then print it
        if word_group_flag is True:
            output_device.write("\n")
            for word_group in d["word-group"]:
                print_yellow(word_group["text"], output_device)
                output_device.write(" " + word_group["meaning"] + "\n")

    return

def get_file_dir():
    """
    Returns the directory of the current python file
    
    :return: str 
    """
    return os.path.dirname(os.path.abspath(__file__))

# This is the file we keep under the same directory as the file
# to record the path that the utility has been installed
PATH_FILE_NAME = "INSTALL_PATH"
def get_path_file_path():
    """
    This function opens the path file path (the file that records the installation path)
    
    :return: str
    """
    # First check whether the file already exists as a flag to
    # indicate previous installation
    current_path = get_file_dir()
    # This is the abs path for the flag
    path_file_path = os.path.join(current_path, PATH_FILE_NAME)
    return path_file_path

DEFAULT_INSTALL_DIR = "/usr/local/bin"
INSTALL_FILE_NAME = "define"

def install():
    """
    Installs a shortcut as "define" command for the current user. This function
    will write a file under the directory of this script for delete to work.
    
    :return: int; 0 if success; Otherwise fail 
    """
    # This is the path in which the installation information is stored
    path_file_path = get_path_file_path()

    # Check if it is a directory then something is wrong and installation
    # could not proceed
    if os.path.isdir(path_file_path) is True:
        print("Path %s could not be a directory - installation fail" %
              (path_file_path, ))
        return 1
    elif os.path.isfile(path_file_path) is True:
        # Otherwise just read the file and check whether the path
        # is still valid
        fp = open(path_file_path, "r")
        line = fp.read()
        fp.close()

        # If there is a previous installation then prompt the user to
        # uninstall it first
        if os.path.isfile(line) is True:
            print("Found a previous installation in %s. Please run --uninstall first" %
                  (line, ))
        else:
            print("Found an invalid installation in %s. Please manually delete it first" %
                  (line, ))

        return 1

    # If there are extra arguments then we use the one after --install command
    # as the path to which we install
    if len(sys.argv) > 2:
        # Need to expand the user and variables like a shell
        install_dir = os.path.expandvars(os.path.expanduser(sys.argv[2]))
    else:
        install_dir = DEFAULT_INSTALL_DIR

    # Then make it an absolute path
    install_dir = os.path.abspath(install_dir)

    # Check whether we have permission to this directory
    if os.access(install_dir, os.W_OK) is False:
        print("Access to \"%s\" denied. Please try sudo" %
              (install_dir, ))
        return 1

    if os.path.isdir(install_dir) is False:
        print("Install path %s is invalid. Please choose a valid one" %
              (install_dir, ))
        return 1

    # Join these two as the path of the file we write into
    install_file_path = os.path.join(install_dir, INSTALL_FILE_NAME)

    # Check whether there is already an utility with the same name
    # Since we already checked installation of this utility before
    # then this should be a name conflict rather than another
    # installation
    if os.path.isfile(install_file_path) is True:
        print("There is already a \"define\" at location %s; please check whether it is a name conflict" %
              (install_file_path, ))
        return 1

    # Get the absolute path of this file and write a bash script
    current_file = os.path.abspath(__file__)
    fp = open(install_file_path, "w")
    fp.write("#!/bin/bash\n")
    fp.write("python %s $@" % (current_file, ))
    fp.close()

    # Also usable by other users
    os.chmod(install_file_path, stat.S_IRWXO | stat.S_IRWXG | stat.S_IRWXU)

    fp = open(path_file_path, "w")
    fp.write(install_file_path)
    fp.close()

    print("Install successful")

    return 0

def uninstall():
    """
    This function uninstalls the "define" utility. We use the path file to
    find the location we have previously installed the utility
    
    :return: int 
    """
    # This is the path to the path file
    path_file_path = get_path_file_path()
    if os.path.isdir(path_file_path) is True:
        print("Path %s could not be a directory - please manually delete it" %
              (path_file_path, ))
        return 1
    elif os.path.isfile(path_file_path) is False:
        print("Did not find a previous installation. To install please run with --install option")
        return 1

    # Open the file, read the first line and delete the utility
    fp = open(path_file_path, "r")
    line = fp.read()
    fp.close()

    # If the path recorded in the file is invalid then prompt the user to manually
    # remove it
    if os.path.isfile(line) is False:
        print("Found an invalid installation in %s. Please manually delete %s" %
              (line, INSTALL_FILE_NAME, ))
        return 1

    # This is the installation directory
    install_dir = os.path.dirname(line)
    # Then check for permissions of the containing directory
    if os.access(install_dir, os.W_OK) is False:
        print("Access to \"%s\" denied. Please try sudo" %
              (install_dir, ))
        return 1

    # Try to remove the file and catch any exception thrown
    # by the routine
    current_file = None
    try:
        current_file = line
        os.unlink(current_file)
        current_file = path_file_path
        os.unlink(current_file)
    except OSError:
        print("Fail to remove file: %s" %
              (current_file, ))
        return 1

    print("Uninstall successful")

    return 0

def cmd_trim_cache():
    """
    This function processes the command line argument --trim-cache, and internally
    calls trim_cache() to randomly delete entries from the cache
    
    :return: None 
    """
    if len(sys.argv) == 2:
        limit = 0
    else:
        try:
            # Use the third argument as the limit and try to convert it
            # from a string to integer
            limit = int(sys.argv[2])
        except ValueError:
            print("Invalid limit \"%s\". Please specify the correct limit." %
                  (sys.argv[2], ))
            return 1

    if limit < 0:
        print("Invalid limit: %d. Please specify a positive integer" %
              (limit, ))
        return 1

    ret = trim_cache(os.path.join(get_file_dir(), CACHE_DIRECTORY), limit)
    print("Deleted %d entry/-ies" % (ret, ))

    return 0

def cmd_ls_cache():
    """
    This function prints cache entries. One word per line
    
    :return: None 
    """
    cache_file_list = get_cache_file_list(os.path.join(get_file_dir(), CACHE_DIRECTORY))
    for name in cache_file_list:
        base_name = os.path.splitext(os.path.basename(name))[0]
        print(base_name)

    return 0

def cmd_ls_define():
    """
    This function prints the current directory we install the utility
    If the utility is not installed or if the installation is invalid nothing is printed.
    
    :return: None 
    """
    path_file_path = get_path_file_path()
    if os.path.isfile(path_file_path) is False:
        return 1

    # This is the location where we install the utility
    fp = open(path_file_path, "r")
    line = fp.read()
    fp.close()

    # If the installation is invalid also return
    if os.path.isfile(line) is False:
        return 1

    print(line)

    return 0

#####################################################################
# The following implements interactive mode
#####################################################################

class InterfaceError(BaseException):
    """
    This is the error thrown for any unhandled error within the interface
    """
    def __init__(self, message):
        """
        Initialize the exception object
        
        :param message: A string message
        """
        self.message = message
        return

    def __str__(self):
        """
        Extracts the string message of the exception
        
        :return: str
        """
        return self.message

    __repr__ = __str__

def interactive_mode():
    """
    This function initializes interactive mode and functions as the dispatching
    engine for the event driven curses library
    
    It only exists when the mode is exited
    
    :return: None
    """
    # Import it here to avoid extra overhead even if we do not use interactive mode
    import curses

    class TextArea:
        """
        This class defines a text area that could:
            (1) Hold multi-line text
            (2) Adjust the range of rows displayed according to the actual dimension
                of the text area (vertical)
            (3) Automatic wrap-back of rows if text area row length is less than the 
                actual line length (horizontal)
        """
        def __init__(self, context, row_num, col_num, start_row, start_col):
            """
            Initialize the dimension of the text area. We need its size and absolute position
            on the screen, which should be within the screen
            
            :param context: The context object
            :param row_num: The height of the control
            :param col_num: The width of the control
            :param start_row: Absolute row of the text area on the screen
            :param start_col: Absolute column of the text area on the screen
            """

            # Check rows and cols to make sure it is inside the screen
            if row_num + start_row >= context.get_screen_row_num():
                raise InterfaceError("TextArea rows out of screen")
            elif col_num + start_col >= context.get_screen_col_num():
                raise InterfaceError("TextArea columns out of screen")

            self.context = context

            self.row_num = row_num
            self.col_num = col_num
            self.start_row = start_row
            self.start_col = start_col

            # This is a list of pages that can be displayed at a time
            # Its content is another list which contains lines (i.e. the line list)
            self.page_list = [[]]

            return

        @staticmethod
        def get_char_width(ch):
            """
            This function returns the width of a character, supporting unicode. 
            Our rule is that, for characters within 0 - 255 we always treat it as 
            having length 1; For other characters we treat it as having length 2
            
            :param ch: Single unicode or str object
            :return: int (1 or 2)
            """
            # If ch is more than one character this will pop up an error
            value = ord(ch)
            if 0 <= value < 256:
                return 1
            else:
                return 2

        def _append_line(self, s):
            """
            This function appends a line into the line list, adding a new page
            if the current line list is full
            
            Note that an empty unicode string represents new line.
            
            :param s: The string get added; must be unicode
            :return: None
            """
            # always try to append to the last page
            last_page = self.page_list[-1]
            assert(len(last_page) <= self.row_num)
            # If the last page has already been filled then we need to
            # create a new page and append it to the page list
            if len(last_page) == self.row_num:
                self.page_list.append([])
                # Change the last page to the page we just appended
                last_page = self.page_list[-1]

            # At last just append the last page
            last_page.append(s)

            return

        def add_line(self, s):
            """
            This function adds one line into the page, and will create new pages if the line
            is splitted into multiple printed lines
            
            :param s: Must be a str or unicode string. We will decode() it to unicode anyway
            :return: None 
            """
            # Decode it into unicode no matter what is the original format
            try:
                s = s.decode()
            except (ValueError, AttributeError):
                pass

            # For empty line and single new line just make it as an empty line
            if len(s) == 0:
                self._append_line(u"")
                return
            elif len(s) == 1 and s[0] == u'\n':
                self._append_line(u"")
                return
            elif s[-1] == u"\n":
                # Strip the last new line character from the string
                s = s[:-1]

            # First pass makes sure there is not new line character
            # in the string
            for ch in s:
                if ch == u"\n":
                    raise InterfaceError("Could not use new line character in add_line()")

            # Actual width
            current_width = 0
            # Index that we start the physical line
            start_index = 0
            # Number of code points we have processed
            current_index = 0
            # Then compute the width of the string and
            for ch in s:
                width = self.get_char_width(ch)
                # If the string will exceed the current line then we
                # start a new line
                if current_width + width + 1 >= self.col_num:
                    assert(current_index > start_index)
                    # Since current index has not been added we truncate
                    # at current index
                    self._append_line(s[start_index:current_index])

                    start_index = current_index
                    current_width = 0

                # This will be executed even if we append a new line
                current_index += 1
                current_width += width

            # And then add what was remained there
            if current_index > start_index:
                # Since current index has not been added we truncate
                # at current index
                self._append_line(s[start_index:current_index])

            return

        def add_block(self, s):
            """
            Adds a text block to be displayed. The block might be divided into
            lines and pages if its length and width exceeds the dimension of the 
            text area
            
            :param s: The string to be added. Can be a str object or unicode string
            :return: None 
            """
            # Try to decode it, and if any problem occurs we
            # just use the original string
            try:
                s = s.decode()
            except (ValueError, AttributeError):
                pass

            line_list = s.split(u"\n")
            for line in line_list:
                self.add_line(line)

            return

        def display_page(self, page_num):
            """
            This function displays the content of a page given the page num. Page num must not 
            exceed the actual number of pages we have
            
            :param page_num: The page number. Start with 0 
            :return: None
            """
            # Check the validity of the page num
            if page_num >= len(self.page_list):
                raise InterfaceError("Page number %d does not exist" % (page_num, ))

            line_list = self.page_list[page_num]
            current_row = 0
            for line in line_list:
                # These two are absolute numbers
                abs_start_row = self.start_row + current_row
                abs_start_col = self.start_col

                self.context.print_str(abs_start_row, abs_start_col, line)

                current_row += 1

            return

        def clear_display(self):
            """
            This function clears the printing area by filling it with space character
            The cursor is not changed after this operation because we save the cursor
            
            :return: None
            """
            self.context.push_cursor()
            # For each line, print empty string
            for row in range(self.start_row, self.start_row + self.row_num):
                self.context.print_str(row, self.start_col, " " * self.col_num)
            self.context.pop_cursor()
            return

        def clear_content(self):
            """
            This function clears the content of the text area by removing all pages and lines.
            Existing contents on the page is not affected
            
            :return: None
            """
            # Restore it to a list of empty pages
            self.page_list = [[]]

            return

        def locate_cursor_to_begin(self):
            """
            This function locates the cursor to the beginning of the text area, i.e. row 0
            column 0
            
            :return: None 
            """
            self.context.stdscr.move(self.start_row, self.start_col)
            return

    class Context:
        """
        This class represents the context object used by interactive mode
        """
        # These are color indices we use for specifying the foreground color
        COLOR_MIN = 1
        COLOR_RED = 1
        COLOR_GREEN = 2
        COLOR_BLUE = 3
        COLOR_YELLOW = 4
        COLOR_MAX = 4

        KEY_ESC = 27
        KEY_ENTER = 10
        KEY_BACK = 263
        KEY_PLUS = 61
        KEY_MINUS = 45
        KEY_HOME = 262

        # This is the row number for input line
        ROW_INPUT_LINE = 3
        # This is the column where the input string should start
        COL_INPUT_START = 8

        # Minimum number of rows required to start this interface
        MIN_ROW_NUM = 10
        # Minimum number of columns required to start this interface
        MIN_COL_NUM = 15

        def __init__(self, stdscr):
            """
            Initializes the context object
            :param stdscr: Global window object
            """
            self.stdscr = stdscr

            # Unpack the returned tuple into col and row numbers
            self.row_num, self.col_num = stdscr.getmaxyx()
            # Check the dimension of the interface
            if self.row_num < self.MIN_ROW_NUM:
                raise InterfaceError("Window should have at least %d rows" % (self.MIN_ROW_NUM, ))
            elif self.col_num < self.MIN_COL_NUM:
                raise InterfaceError("Window should have at least %d columns" % (self.MIN_COL_NUM, ))

            # This is the maximum length allowed for the input string
            # We should treat this as a constant
            self.input_max_length = self.col_num - self.COL_INPUT_START - 2

            # This represents what we need to draw for the status
            self.status_dict = {}

            # This is the input string
            self.input_str = ""
            # Whether do we allow input
            self.input_blocked = False

            # This is a stack of cursor positions that is saved by calling
            # corresponding routines
            self.cursor_stack = []

            return

        def push_cursor(self):
            """
            Push a (row, col) tuple to the cursor stack
            :return: None
            """
            self.cursor_stack.append(self.get_cursor_pos())
            return

        def pop_cursor(self):
            """
            This function pops a cursor position and change the cursor to it
            
            :return: None 
            """
            # Check whether the stack is empty
            if len(self.cursor_stack) == 0:
                raise InterfaceError("Cursor stack is empty")

            # Access last and then delete the position
            row, col = self.cursor_stack.pop()
            self.stdscr.move(row, col)

            return

        def get_screen_row_num(self):
            """
            Returns the screen row number
            :return: int
            """
            return self.row_num

        def get_screen_col_num(self):
            """
            Returns the screen column number
            :return: int
            """
            return self.col_num

        # These two are used to mark the begin and end of colored outputs
        COLOR_BEGIN_MARKER = u"\033[1;" # Followed by [dd]m where [dd] are two digits
        COLOR_END_MARKER = u"\033[0m"

        def print_str(self, row, col, s, attr=None):
            """
            This function prints a string at row, col. This function also deals with colors
            
            :param row: Could be minus number. -1 means last line
            :param col: Could be minus number. -1 means last column
            :param s: 
            :return: None
            """
            # Deal with the cases when it is less than zero
            if row < 0:
                row = self.row_num + row
            if col < 0:
                col = self.col_num + col

            # This is the current index we are working on
            start_index = 0
            while True:
                # Find the color begin index if there is one
                color_begin_marker_index = s.find(self.COLOR_BEGIN_MARKER)
                if color_begin_marker_index == -1:
                    break

                # Then extract the next three characters from the input string
                color_code_start_index = color_begin_marker_index + len(self.COLOR_BEGIN_MARKER)
                color_code = s[color_code_start_index:color_code_start_index + 3]
                if len(color_code) != 3:
                    raise InterfaceError("Invalid color code")

                if color_code[-1]

                # Then find the color end marker index
                color_end_marker_index = s.find(self.COLOR_END_MARKER, color_begin_marker_index)

                if color_end_marker_index == -1:


            if attr is not None:
                self.stdscr.addstr(row, col, s.encode("utf-8"), attr)
            else:
                self.stdscr.addstr(row, col, s.encode("utf-8"))

            return

        @classmethod
        def get_color(cls, color_index):
            """
            This function returns the color attribute that could be applyed
            to strings as its attribute
            
            :param color_index: The color code defined in the class 
            :return: attribute object
            """
            assert(cls.COLOR_MIN <= color_index <= cls.COLOR_MAX)
            return curses.color_pair(color_index)

        def update_status(self):
            """
            This function updates the status bar
            
            :return: None 
            """
            # Save cursor location
            self.push_cursor()

            # Delete everything currently on the status line first
            self.print_str(-2, 1, " " * (self.col_num - 2))

            key_list = list(self.status_dict.keys())
            key_list.sort()
            offset = 1
            for key in key_list:
                key_length = len(key) + 2
                self.print_str(-2, offset, key + ": ", self.get_color(self.COLOR_RED))
                offset += key_length

                value = self.status_dict[key]
                value_length = len(value) + 1
                self.print_str(-2, offset, value + " ")
                offset += value_length

            # Restore cursor location
            self.pop_cursor()
            return

        def locate_cursor_to_input(self):
            """
            This function changes the location of the cursor to match the length of the string
            and also to keep the focus on the input box
            
            :return: None
            """
            cursor_row = self.ROW_INPUT_LINE
            cursor_col = len(self.input_str) + self.COL_INPUT_START

            # Call cursor method to move the input cursor symbol
            self.stdscr.move(cursor_row, cursor_col)

            return

        def get_cursor_pos(self):
            """
            This function returns the row and col of the current cursor on the 
            main window
            
            :return: tuple(row, col) 
            """
            return self.stdscr.getyx()

    def init_color(context):
        """
        This function initializes colors using the constants from the context 
        class variable

        :return: None
        """
        del context

        curses.init_pair(Context.COLOR_RED, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(Context.COLOR_GREEN, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(Context.COLOR_BLUE, curses.COLOR_BLUE, curses.COLOR_BLACK)
        curses.init_pair(Context.COLOR_YELLOW, curses.COLOR_YELLOW, curses.COLOR_BLACK)

        return

    def draw_frame(context):
        """
        This function draws the title at the top of the window. This is only called once
        in order to 
        
        :param context: The context object that holds stdscr and other
                        important parameters
        :return: None 
        """
        # Draws the title
        title = u"YouDao Online Dictionary Client (有道词典)"
        title_col_offset = (context.col_num - len(title)) >> 1
        context.print_str(1, title_col_offset, title, curses.A_BOLD | context.get_color(context.COLOR_YELLOW))
        context.print_str(2, 1, "-" * (context.col_num - 2))

        # Then draws the status bar
        context.print_str(-3, 1, "-" * (context.col_num - 2))

        # Draws the input prompt
        context.print_str(Context.ROW_INPUT_LINE, 1, "Input: ")

        return

    class OutputDevice:
        """
        This class aggregates write() method's input as a string
        and converts to a string when requested
        """
        def __init__(self): self.s = u""
        def write(self, s): self.s += s
        def __str__(self): return self.s
        __repr__ = __str__

    def draw_input(context, ch):
        """
        This function draws the input pad for querying words
        
        :param context: The Context object
        :param ch: The control code for the input
        :return: None 
        """
        # Store the character's integer value in status bar
        context.status_dict["Keyboard"] = str(ch)
        context.status_dict.pop("Error", None)
        context.update_status()

        # If it belongs to ASCII character type then add it to the input string
        # of class context and update the input pad
        if ord("a") <= ch <= ord("z") or ord("A") <= ch <= ord("Z"):
            # If input is blocked then print an info in the status bar and exit
            if context.input_blocked is True:
                context.status_dict = {"Error": "Please wait for result"}
                context.update_status()
            else:
                assert(len(context.input_str) <= context.input_max_length)
                # If the input string is too long we simply prompt an error
                # and discard the input
                if len(context.input_str) == context.input_max_length:
                    context.status_dict["Error"] = \
                        "Input too long (limit = %d)" % (context.input_max_length, )
                    # Reflect it to the status bar
                    context.update_status()
                else:
                    context.print_str(Context.ROW_INPUT_LINE,
                                      len(context.input_str) + Context.COL_INPUT_START,
                                      chr(ch))
                    context.input_str += chr(ch)
        elif ch == Context.KEY_BACK:
            current_input_len = len(context.input_str)
            # Back only if there is no current input
            if current_input_len != 0:
                # Use a space character to overwrite the deleted character
                context.print_str(Context.ROW_INPUT_LINE,
                                  len(context.input_str) + Context.COL_INPUT_START - 1,
                                  " ")
                # Trim the actual string
                context.input_str = context.input_str[:-1]
            else:
                context.status_dict["Error"] = "No character to delete"
                context.update_status()
        elif ch == Context.KEY_ENTER:
            context.input_blocked = True

            # If enter is pressed we need to initialize a request and wait for result
            # In the mean time all inputs are blocked
            w = context.input_str
            d_list = check_in_cache(w)
            output_device = OutputDevice()
            if d_list is None:
                context.status_dict = {"Progressing": "Querying online source..."}
                d_list = get_collins_dict(parse_webpage(get_webpage(w)))
                if d_list is None:
                    context.status_dict = {"Error": "Word not found"}
                else:
                    context.status_dict = {"Query": "Finished successfully"}
                    collins_pretty_print(d_list, output_device)
            else:
                context.status_dict = {"Query": "Satisfied from local cache"}
                collins_pretty_print(d_list, output_device)

            # We change status in every branch, so refresh it here
            context.update_status()

            # Add it into the text area and then print it
            context.text_area.add_block(output_device.s)
            context.text_area.display_page(0)

            # Allow input
            context.input_blocked = False

        # No matter what happens this is always called
        context.locate_cursor_to_input()

        return

    def main(stdscr):
        """
        This function defines the main function for event loop. It will be 
        passed as the call back to curses library. The curses library will pass in
        a stdscr object
        
        :return: None
        """
        # This is a context object that will be used globally
        context = Context(stdscr)

        # This is the main place we display text
        text_area = TextArea(context,
                             context.get_screen_row_num() - 7,
                             context.get_screen_col_num() - 2,
                             5,
                             1)
        context.text_area = text_area
        text_area.clear_display()

        context.stdscr.border()
        # This is only done once no matter how many context objects we create
        init_color(context)
        # Draws the frame of the window including title and status bar
        draw_frame(context)

        while True:
            ch = stdscr.getch()
            # Exits on ESCAPE key
            if ch == Context.KEY_ESC:
                break
            else:
                # This draws the input pad
                draw_input(context, ch)

        return

    # Start the wrapper and handles initialization, tearing down
    # and exception handling
    curses.wrapper(main)

    return

# This dict object maps the argument from keyword to the maximum number
# of arguments (incl. optional arguments)
# This is only used with options that do not carry words
CONTROL_COMMAND_DICT = {
    "--install": 1,
    "--uninstall": 0,
    "--ls-dir": 0,
    "--trim-cache": 1,
    "--ls-cache": 0,
    "--help": 0,
    "-h": 0,
    "--ls-define": 0,
    "-i": 0,
    "--interactive": 0,
}

def process_args():
    """
    This function processes arguments
    
    :return: None 
    """
    global verbose_flag
    global m5_flag
    global debug_flag
    global force_flag
    global no_add_flag
    global word_group_flag

    if len(sys.argv) < 2:
        print(USAGE_STRING)
        sys.exit(0)

    # In case the user put an option before the word
    if sys.argv[1][0] == "-" and \
       sys.argv[1] not in CONTROL_COMMAND_DICT:
        print(USAGE_STRING)
        sys.exit(0)

    # This is the index of the argv item we are currently on
    argv_index = -1
    for arg in sys.argv:
        argv_index += 1

        # Control commands must be the first argument;
        # Otherwise error
        optional_arg_num = CONTROL_COMMAND_DICT.get(arg, None)
        if optional_arg_num is not None:
            if argv_index != 1:
                print("Please use control command \"%s\" always as the first argument" %
                      (arg, ))
                sys.exit(1)
            elif len(sys.argv) > (optional_arg_num + 2):
                print("Please use control command \"%s\" with correct argument (expecting %d)" %
                      (arg, optional_arg_num, ))
                sys.exit(1)

        if arg == "-v" or arg == "--verbose":
            verbose_flag = True
        elif arg == "-m5":
            m5_flag = True
        elif arg == "-h" or arg == "--help":
            print(USAGE_STRING)
            sys.exit(0)
        elif arg == "--install":
            ret = install()
            sys.exit(ret)
        elif arg == "--uninstall":
            ret = uninstall()
            sys.exit(ret)
        elif arg == "--ls-dir":
            # This command will print absolute directory of this file
            # and then exit
            print(get_file_dir())
            sys.exit(0)
        elif arg == "--trim-cache":
            # This processes the cmd line argument
            ret = cmd_trim_cache()
            sys.exit(ret)
        elif arg == "--ls-cache":
            ret = cmd_ls_cache()
            sys.exit(ret)
        elif arg == "--ls-define":
            ret = cmd_ls_define()
            sys.exit(ret)
        elif arg == "-i" or arg == "--interactive":
            # Enters interactive mode until it returns
            # We also catch interface error to handle those errors
            # that must be handled outside the interface
            try:
                interactive_mode()
            except InterfaceError as e:
                print("Error: " + str(e))

            sys.exit(0)
        elif arg == "--debug":
            debug_flag = True
        elif arg == "--force":
            force_flag = True
        elif arg == "--no-add":
            no_add_flag = True
        elif arg == "-g" or arg == "--word-group":
            word_group_flag = True

    dbg_printf("Debug flag: %s", debug_flag)
    dbg_printf("m5 flag: %s", m5_flag)
    dbg_printf("verbose flag: %s", verbose_flag)
    dbg_printf("force flag: %s", force_flag)
    dbg_printf("no add flag: %s", no_add_flag)
    dbg_printf("word group flag: %s", word_group_flag)

    return

USAGE_STRING = """
Youdao Online Dictionary Parser
===============================

Usage (without installing): python youdao_dict.py [word] [--options]
Usage (after installation): define [word] [--options]

The following must be used with [word] being the first argument

-v/--verbose    Also show examples
-g/--word-group Also show word group and their meanings
-m5             Only Display the first 5 meaning of each word
--debug         Shows debug message (e.g. reasons for parsing failure)
                Used for developer to debug.
--force         Ignore cached content
--no-add        Do not add the word into the cache under all circumstances

The following is used without specifying the [word]

-h/--help         Display this message
--install [dir]   Install this as an utility, "define". 
                  Optional argument specifies the location. 
--uninstall       Uninstall the "define" utility. This removes the first "define"
                  utility that appears under PATH

--trim-cache [#]  Remove cache contents until there are [#] of entry/-ies left
                  The number must be an integer greater than or equal to 0
                  Default value is 0, which means deleting all contents from 
                  the cache
--ls-cache        List words in the cache. One word each line
--ls-define       Print the absolute file name of the utility
--ls-dir          Print the directory of this file

-i/--interactive  Start in interactive mode; Press ESC to exit
"""
verbose_flag = False
word_group_flag = False
m5_flag = False
debug_flag = False
force_flag = False
no_add_flag = False

process_args()
query_word = sys.argv[1]

# If it is None after checking the cache then we send HTTP
meaning_dict_list = None
if force_flag is False:
    meaning_dict_list = check_in_cache(query_word)
else:
    dbg_printf("Ignoring the cache and to force an HTTP request")

if meaning_dict_list is None:
    collins_pretty_print(get_collins_dict(parse_webpage(get_webpage(query_word))))
else:
    dbg_printf("Serving word \"%s\" from the cache", query_word)
    collins_pretty_print(meaning_dict_list)