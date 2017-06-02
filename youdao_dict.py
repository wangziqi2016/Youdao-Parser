
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
      ]
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
    for tree in top_level_list:
        wt_index += 1
        # We append this into a list
        ret = {}

        # This <h4> contains the main word, the pronunciation
        h4 = tree.find("h4")
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
        li_list = tree.find_all("li")
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
                        if content.name == "b":
                            meaning += ("<red>" + " ".join(content.text.split()) + "</red> ")
                        else:
                            meaning += " ".join(content.text.split())
                    else:
                        meaning += " ".join(content.split())

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

        # Set the actual key on the webpage
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
        delta = current_cache_size - limit + 1
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
        ret = trim_cache(cache_dir, CACHE_MAX_ENTRY)
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
        return None

    # This is the word file
    word_file = os.path.join(cache_dir, "%s.json" % (word,))
    # If the file exists then ignore it
    if os.path.isfile(word_file) is False:
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
def print_red(text):
    """
    Prints the given text in read fore color
    
    :param text: The text to be printed
    :return: None
    """
    sys.stdout.write(RED_TEXT_START)
    sys.stdout.write(text)
    sys.stdout.write(RED_TEXT_END)

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

def collins_pretty_print(dict_list):
    """
    Prints a dict object in pretty form. The input dict object may
    be None, in which case we skip printing
    
    :return: None
    """
    global verbose_flag
    global m5_flag

    if dict_list is None:
        return

    for d in dict_list:
        print_red(d["word"])
        sys.stdout.write("        ")

        # Write the frequency if it has one
        freq = d["frequency"]
        if freq != -1:
            sys.stdout.write("[%s]        " % ("*" * freq, ))

        sys.stdout.write(d["phonetic"])
        sys.stdout.write("\n")

        counter = 1
        for meaning in d["meanings"]:
            if m5_flag is True and counter == 6:
                return

            sys.stdout.write("%d. (%s) " % (counter, meaning["category"]))
            counter += 1

            text = process_color(meaning["text"])
            sys.stdout.write(text)

            sys.stdout.write("\n")

            if verbose_flag is True:
                for example in meaning["examples"]:
                    sys.stdout.write("    - ")
                    sys.stdout.write(example["text"])
                    sys.stdout.write("\n")
                    sys.stdout.write("      ")
                    sys.stdout.write(example["translation"])
                    sys.stdout.write("\n")

        sys.stdout.write("\n")

    return

def get_file_dir():
    """
    Returns the directory of the current python file
    
    :return: str 
    """
    return os.path.dirname(os.path.abspath(__file__))

DEFAULT_INSTALL_DIR = "/usr/local/bin"
INSTALL_FILE_NAME = "define"
def install():
    """
    Installs a shortcut as "define" command for the current user using the pwd
    
    :return: None 
    """
    # If there are extra arguments then we use the one after --install command
    # as the path to which we install
    if len(sys.argv) > 2:
        install_dir = sys.argv[2]
    else:
        install_dir = DEFAULT_INSTALL_DIR

    # Check whether we have permission to this directory
    if os.access(install_dir, os.W_OK) is False:
        print("Access denied. Please try sudo (%s)" %
              (install_dir, ))
        return

    if os.path.isdir(install_dir) is False:
        print("Install path %s is invalid. Please choose a valid one" %
              (install_dir, ))

    # Join these two as the path of the file we write into
    install_file_path = os.path.join(install_dir, INSTALL_FILE_NAME)

    # Check whether we have already installed the file
    if os.path.isfile(install_file_path) is True:
        print("You have already installed at location %s" % (install_file_path, ))
        return

    # Get the absolute path of this file and write a bash script
    current_file = os.path.abspath(__file__)
    fp = open(install_file_path, "w")
    fp.write("#!/bin/bash\n")
    fp.write("python %s $@" % (current_file, ))
    fp.close()

    # Also usable by other users
    os.chmod(install_file_path, stat.S_IRWXO | stat.S_IRWXG | stat.S_IRWXU)

    print("Install successful")

    return

def uninstall():
    """
    This function uninstalls the "define" utility. We search the PATH variable
    and delete the first file that occurs under the path
    
    :return: None 
    """
    # This is a list of paths that the system will search
    # if a name without directory is executed
    path_list = os.environ.get('PATH').split(os.pathsep)
    for path in path_list:
        # This is the absolute path to the file that we install
        define_file_path = os.path.join(path, INSTALL_FILE_NAME)

        # Find the first file that appears and remove it
        if os.path.isfile(define_file_path) is True:
            if os.access(path, os.W_OK) is False:
                print("Access denied. Please try sudo (%s)" %
                      (path, ))
                return

            os.unlink(define_file_path)
            print("Uninstall successful (%s)" %
                  (define_file_path, ))
            break
    else:
        print("Did not find the utility - have you previously installed?")

    return

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
            limit = int(argv[2])
        except ValueError:
            print("Invalid limit \"%s\". Please specify the correct limit." %
                  (argv[2], ))
            sys.exit(1)

    if limit < 0:
        print("Invalid limit: %d. Please specify a positive integer" %
              (limit, ))
        sys.exit(1)

    ret = trim_cache(os.path.join(get_file_dir(), CACHE_DIRECTORY), limit)
    print("Deleted %d entry/-ies" % (ret, ))

    return

# This dict object maps the argument from keyword to the maximum number
# of arguments (incl. optional arguments)
CONTROL_COMMAND_DICT = {
    "--install": 1,
    "--uninstall": 0,
    "--cd": 0,
    "--clear-cache": 1
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
            elif len(sys.argv) != (optional_arg_num + 2):
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
            install()
            sys.exit(0)
        elif arg == "--uninstall":
            uninstall()
            sys.exit(0)
        elif arg == "--cd":
            # This command will print absolute directory of this file
            # and then exit
            print(get_file_dir())
            sys.exit(0)
        elif arg == "--trim-cache":
            # This processes the cmd line argument
            cmd_trim_cache()
            sys.exit(0)
        elif arg == "--debug":
            debug_flag = True
        elif arg == "--force":
            force_flag = True

    dbg_printf("Debug flag: %s", debug_flag)
    dbg_printf("m5 flag: %s", m5_flag)
    dbg_printf("verbose flag: %s", verbose_flag)
    dbg_printf("force flag: %s", force_flag)

    return

USAGE_STRING = """
Youdao Online Dictionary Parser
===============================

Usage: python youdao_dict.py [word] [options]

The following must be used with [word] being the first argument

-h/--help    Display this message
-v/--verbose Also show examples
-m5          Only Display the first 5 meaning of each word
--debug      Shows debug message (e.g. reasons for parsing failure)
             Used for developer to debug.
--force      Ignore cached content

The following is used without specifying the [word]

--install  [dir]  Install this as an utility, "define". 
                  Optional argument specifies the location. 
--uninstall       Uninstall the "define" utility. This removes the first "define"
                  utility that appears under PATH
--cd              Print the directory of this file

--trim-cache [#]  Remove cache contents until there are [#] of entry/-ies left
                  The number must be an integer greater than or equal to 0
                  Default value is 0, which means deleting all contents from 
                  the cache
"""
verbose_flag = False
m5_flag = False
debug_flag = False
force_flag = False

process_args()
query_word = sys.argv[1]

# If it is None after checking the cache then we send HTTP
meaning_dict_list = None
if force_flag is False:
    check_in_cache(query_word)

if meaning_dict_list is None:
    collins_pretty_print(get_collins_dict(parse_webpage(get_webpage(query_word))))
else:
    collins_pretty_print(meaning_dict_list)