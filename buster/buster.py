"""Ghost Buster. Static site generator for Ghost.

Usage:
  buster.py setup [--gh-repo=<repo-url>] [--dir=<path>]
  buster.py generate [--domain=<local-address>] [--dir=<path>] [--web-url=<web-url>]
  buster.py preview [--dir=<path>]
  buster.py deploy [--dir=<path>]
  buster.py add-domain <domain-name> [--dir=<path>]
  buster.py (-h | --help)
  buster.py --version

Options:
  -h --help                 Show this screen.
  --version                 Show version.
  --dir=<path>              Absolute path of directory to store static pages.
  --domain=<local-address>  Address of local ghost installation
  [default: localhost:2368].
  --web-url=<web-url>       Your Blog Website URL (Fixed for Blog RSS).
  --gh-repo=<repo-url>      URL of your gh-pages repository.

"""
import http.server
import socketserver
import fnmatch
import os
import re
import shutil
import sys
from time import gmtime, strftime

from docopt import docopt
from git import Repo
from pyquery import PyQuery


def mkdir_p(path):
    if not os.path.exists(path):
        os.makedirs(path)


def main():
    arguments = docopt(__doc__, version='0.1.3')
    if arguments['--dir'] is not None:
        static_path = arguments['--dir']
    else:
        static_path = os.path.join(os.getcwd(), 'static')

    if arguments['--web-url'] is not None:
        web_url = "{}".format(arguments['--web-url'])
    else:
        web_url = None

    domain = arguments['--domain']
    if arguments['generate']:
        command = ("wget "
                   "--level=0 "  # set level to infinitive
                   "--recursive "  # follow links to download entire site
                   "--convert-links "  # make links relative
                   "--page-requisites "  # grab everything: css/in-lined images
                   "--no-parent "  # don't go to parent level
                   "--directory-prefix {1} " # download content to static/folder
                   "--no-host-directories "  # don't create domain named folder
                   "--restrict-file-name=unix "  # don't escape query string
                   "{0}").format(domain, static_path)
        os.system(command)

        # copy sitemap files since Ghost 0.5.7
        base_command = "wget --convert-links --page-requisites --no-parent " \
                       "--directory-prefix {1} --no-host-directories " \
                       "--restrict-file-name=unix {0}/{2}"
        command = base_command.format(domain, static_path, "sitemap.xsl")
        os.system(command)
        command = base_command.format(domain, static_path, "sitemap.xml")
        os.system(command)
        command = base_command.format(domain, static_path, "sitemap-pages.xml")
        os.system(command)
        command = base_command.format(domain, static_path, "sitemap-posts.xml")
        os.system(command)
        command = base_command.format(domain, static_path,
                                      "sitemap-authors.xml")
        os.system(command)
        command = base_command.format(domain, static_path, "sitemap-tags.xml")
        os.system(command)

        def pullRss(path):
            if path is None:
                baserssdir = os.path.join(static_path, "rss")
                mkdir_p(baserssdir)
                wget_command = ("wget --output-document=" + baserssdir +
                                "/feed.rss {0}/rss/").format(domain)
                os.system(wget_command)
            else:
                for feed in os.listdir(os.path.join(static_path, path)):
                    rsspath = os.path.join(path, feed, "rss")
                    rssdir = os.path.join(static_path, 'rss', rsspath)
                    mkdir_p(rssdir)
                    wget_command = ("wget --output-document=" + rssdir
                                    + "/index.html {0}/" + rsspath).format(
                        domain)
                    os.system(wget_command)

        pullRss("tag")
        pullRss("author")

        # remove query string since Ghost 0.4
        file_regex = re.compile(r'.*?(\?.*)')
        bad_file_regex = re.compile(r'.+\.[0-9]{1,2}$')
        static_page_regex = re.compile(r"^([\w-]+)$")

        for root, dirs, filenames in os.walk(static_path):
            for filename in filenames:
                if file_regex.match(filename):
                    newname = re.sub(r'\?.*', '', filename)
                    print("Rename", filename, "=>", newname)
                    os.rename(os.path.join(root, filename),
                              os.path.join(root, newname))
                if bad_file_regex.match(filename):
                    os.remove(os.path.join(root, filename))

                # if we're inside static_path or static_path/tag, rename
                # extension-less files to filename.html
                if (root == static_path
                    or root == os.path.join(static_path, 'tag'))\
                        and static_page_regex.match(filename)\
                        and filename != 'CNAME':
                    newname = filename + ".html"
                    newpath = os.path.join(root, newname)
                    try:
                        os.remove(newpath)
                    except OSError:
                        pass
                    shutil.move(os.path.join(root, filename), newpath)

        # remove superfluous "index.html" from relative hyperlinks found in text
        abs_url_regex = re.compile(r'^(?:[a-z]+:)?//', flags=re.IGNORECASE)
        bad_url_regex = bad_file_regex

        def fixLinks(text, parser):
            if text == '':
                return ''
            try:
                d = PyQuery(bytes(bytearray(text, encoding='utf-8')),
                            parser=parser)
            except UnicodeDecodeError:
                d = PyQuery(bytes(bytearray(text)), parser=parser)
            for element in d('a, link'):
                e = PyQuery(element)
                href = e.attr('href')

                if href is None:
                    continue
                if (not abs_url_regex.search(href)) or ('/rss/' in href):
                    new_href = re.sub(r"/([\w-]+)$", r"/\1.html", href)
                    new_href = re.sub(r"^([\w-]+)$", r"\1.html", new_href)
                    if href != new_href:
                        e.attr('href', new_href)
                        print("\t", href, "=>", new_href)

                href = e.attr('href')
                if bad_url_regex.search(href):
                    new_href = re.sub(r'(.+)\.[0-9]{1,2}$', r'\1', href)
                    e.attr('href', new_href)
                    print("\t FIX! ", href, "=>", new_href)
            return "<!DOCTYPE html>\n<html>" + d.html(method='html') + "</html>"

        # fix links in all html files
        for root, dirs, filenames in os.walk(static_path):
            for filename in fnmatch.filter(filenames, "*.html"):
                filepath = os.path.join(root, filename)
                parser = 'html'
                if root.endswith("/rss"):  # rename rss index.html to index.rss
                    parser = 'xml'
                    newfilepath = os.path.join(root, os.path.splitext(filename)[
                        0] + ".rss")
                    os.rename(filepath, newfilepath)
                    filepath = newfilepath
                with open(filepath) as f:
                    filetext = f.read()
                print("fixing links in ", filepath)
                newtext = filetext
                if parser == 'html':
                    newtext = fixLinks(filetext, parser)
                with open(filepath, 'w') as f:
                    try:
                        f.write(newtext)
                    except UnicodeEncodeError:
                        f.write(newtext.encode('utf-8'))

        def trans_local_domain(text):
            modified_text = text.replace('http://localhost:2368', web_url)
            modified_text = modified_text.replace('http://', '//')
            modified_text = re.sub(r'(rss\/)[a-z]+(.html)', r'\1index.rss',
                                   modified_text)

            return modified_text

        def remove_v_tag_in_css_and_html(text):
            modified_text = re.sub(r"%3Fv=[\d|\w]+\.css", "", text)
            modified_text = re.sub(r".js%3Fv=[\d|\w]+", ".js", modified_text)
            modified_text = re.sub(r".woff%3[\d|\w]+", ".woff", modified_text)
            modified_text = re.sub(r".ttf%3[\d|\w]+", ".ttf", modified_text)

            modified_text = re.sub(r"css\.html", "css", modified_text)
            modified_text = re.sub(r"png\.html", "png", modified_text)
            modified_text = re.sub(r"jpg\.html", "jpg", modified_text)

            return modified_text

        for root, dirs, filenames in os.walk(static_path):
            for filename in filenames:
                if filename.endswith(('.html', '.xml', '.css', '.xsl', '.rss')):
                    filepath = os.path.join(root, filename)
                    with open(filepath) as f:
                        filetext = f.read()
                    print("fixing local domain in ", filepath)
                    newtext = trans_local_domain(filetext)
                    newtext = remove_v_tag_in_css_and_html(newtext)
                    with open(filepath, 'w') as f:
                        f.write(newtext)

    elif arguments['preview']:
        os.chdir(static_path)

        Handler = http.server.SimpleHTTPRequestHandler
        httpd = socketserver.TCPServer(("", 9001), Handler)

        print("Serving at port 9000")
        # gracefully handle interrupt here
        httpd.serve_forever()

    elif arguments['setup']:
        if arguments['--gh-repo']:
            repo_url = arguments['--gh-repo']
        else:
            repo_url = input("Enter the Github repository URL:\n").strip()

        # Create a fresh new static files directory
        if os.path.isdir(static_path):
            confirm = input("This will destroy everything inside static"
                            " Are you sure you want to continue? (y/N)").strip()
            if confirm != 'y' and confirm != 'Y':
                sys.exit(0)
            shutil.rmtree(static_path)

        # User/Organization page -> master branch
        # Project page -> gh-pages branch
        branch = 'gh-pages'
        regex = re.compile(".*[\w-]+\.github\.(?:io|com).*")
        if regex.match(repo_url):
            branch = 'master'

        # Prepare git repository
        repo = Repo.init(static_path)
        git = repo.git

        if branch == 'gh-pages':
            git.checkout(b='gh-pages')
        repo.create_remote('origin', repo_url)

        # Add README
        file_path = os.path.join(static_path, 'README.md')
        with open(file_path, 'w') as f:
            f.write(
                '# Blog\nPowered by [Ghost](http://ghost.org)'
                ' and [Buster](https://github.com/manthansharma/buster/).\n')

        print("All set! You can generate and deploy now.")

    elif arguments['deploy']:
        repo = Repo(static_path)
        repo.git.add('.')

        current_time = strftime("%Y-%m-%d %H:%M:%S", gmtime())
        repo.index.commit('Blog update at {}'.format(current_time))

        origin = repo.remotes.origin
        repo.git.execute(['git', 'push', '-u', origin.name,
                          repo.active_branch.name])
        print("Good job! Deployed to Github Pages.")

    elif arguments['add-domain']:
        repo = Repo(static_path)
        custom_domain = arguments['<domain-name>']

        file_path = os.path.join(static_path, 'CNAME')
        with open(file_path, 'w') as f:
            f.write(custom_domain + '\n')

        print("Added CNAME file to repo. Use `deploy` to deploy")

    else:
        print(__doc__)


if __name__ == '__main__':
    main()
