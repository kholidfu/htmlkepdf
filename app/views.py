# author: @sopier
from flask import render_template, request, redirect, send_from_directory
from flask import make_response # untuk sitemap
from app import app
# untuk find_one based on data id => db.freewaredata.find_one({'_id': ObjectId(file_id)})
# atom feed
from werkzeug.contrib.atom import AtomFeed
from bson.objectid import ObjectId 
from filters import slugify, splitter, onlychars, get_first_part, get_last_part, formattime, cleanurl
import datetime
import pymongo
from gridfs import GridFS

from subprocess import Popen, PIPE
import os
from bs4 import BeautifulSoup
import time
import requests

c = pymongo.Connection()
db = c['htmltopdf']
fs = GridFS(db)

@app.template_filter()
def slug(s):
    """ 
    transform words into slug 
    usage: {{ string|slug }}
    """
    return slugify(s)

@app.template_filter()
def split(s):
    """ 
    split string s with delimiter '-' 
    return list object
    usage: {{ string|split }}
    """
    return splitter(s, '-')

@app.template_filter()
def getlast(text, delim=' '):
    """
    get last word from string with delimiter ' '
    usage: {{ string|getlast }}
    """
    return get_last_part(text, delim)

@app.template_filter()
def getfirst(text, delim=' '):
    """
    get first word from string with delimiter '-'
    usage: {{ string|getfirst }}
    """
    return get_first_part(text, delim)

@app.template_filter()
def getchars(text):
    """
    get characters and numbers only from string
    usage: {{ string|getchars }}
    """
    return onlychars(text)

@app.template_filter()
def sectomins(seconds):
    """
    convert seconds to hh:mm:ss
    usage: {{ seconds|sectomins }}
    """
    return formattime(seconds)

@app.template_filter()
def urlcleaner(text):
    """
    clean url from string
    """
    return cleanurl(text)

# handle robots.txt file
@app.route("/robots.txt")
def robots():
    # point to robots.txt files
    return send_from_directory(app.static_folder, request.path[1:])

@app.route("/")
def index():
    numfiles = db.fs.files.find().count()
    return render_template("index.html", numfiles=numfiles)

@app.route("/render")
def render():
    # magic number for unique file name
    magicnum = '_' + str(int(time.time()))

    from urllib import unquote
    query = request.args.get('q')
    url = unquote(query)

    if 'htmlkepdf.com' in url:
        return redirect('/', 301)

    from urlparse import urlparse
    addr = urlparse(url).netloc
    filename = addr.replace('.', '_')

    from readability.readability import Document
    import urllib2
    opener = urllib2.build_opener()
    opener.addheaders = [('User-agent', 'Mozilla/5.0')]
    try:
        html = opener.open(url).read()
    #except HTTPError:
    #    html = urllib2.urlopen(url).read()
    except:
        html = requests.get(url).content
    readable_article = Document(html).summary()
    readable_title = Document(html).short_title()

    # clean up text with bs4
    soup = BeautifulSoup(readable_article)
    readable_article = soup.body(text=True)
    readable_article = ' '.join(readable_article)
    # find meta, just in case readable article is too short
    soup2 = BeautifulSoup(html)
    try:
        metadesc = soup2.find('meta', {'name': 'description'})['content']
    except:
        metadesc = ''
    # error list
    # 1. facebook.com harus pake https

    p1 = Popen('xvfb-run --auto-servernum --server-num=1 python gistfile2.py ' + '"' + url + '"' + ' ' + filename + '.pdf', shell=True, stdout=PIPE, stderr=PIPE, close_fds=True)
    stdout, stderr = p1.communicate() # wait

    retcode = p1.returncode
    if retcode == 0:
        with open(filename + '.pdf') as f:
            # filter data yang masuk, biar gak duplikat
            oid = fs.put(f, content_type='application/pdf', filename=filename+magicnum, title=readable_title, article=readable_article, update=datetime.datetime.now(), url=url, metadesc=metadesc)
        os.remove(filename + '.pdf')
        return redirect('/view/' + str(oid))

    elif retcode == 139:
        p2 = Popen('phantomjs rasterize.js ' + '"' + url + '"' + ' ' + filename + '.pdf', shell=True, stdout=PIPE, stderr=PIPE, close_fds=True)
        stdout, stderr = p2.communicate() # wait

        retcode = p2.returncode
        if retcode == 0:
            with open(filename + '.pdf') as f:
                # filter data yang masuk, biar gak duplikat
                oid = fs.put(f, content_type='application/pdf', filename=filename+magicnum, title=readable_title, article=readable_article, update=datetime.datetime.now(), url=url, metadesc=metadesc)
                os.remove(filename + '.pdf')
                return redirect('/view/' + str(oid))

    else:
        p2 = Popen('phantomjs rasterize.js ' +  '"' + url + '"' + ' ' + filename + '.pdf', shell=True, stdout=PIPE, stderr=PIPE, close_fds=True)
        stdout, stderr = p2.communicate() # wait

        retcode = p2.returncode
        if retcode == 0:
            with open(filename + '.pdf') as f:
                # filter data yang masuk, biar gak duplikat
                oid = fs.put(f, content_type='application/pdf', filename=filename+magicnum, title=readable_title, article=readable_article, update=datetime.datetime.now(), url=url, metadesc=metadesc)
                os.remove(filename + '.pdf')
                return redirect('/view/' + str(oid))

    # else error, tampilkan error di halaman error
    stderror = stderr

    return render_template("error.html", query=query, addr=addr, title=readable_title, stderror=stderror, retcode=retcode)

@app.route("/collections/<id>")
def collection(id):
    oid = id
    out = fs.get(ObjectId(id))
    pdf = out.read()
    filename = out.filename
    title = out.title
    article = out.article
    update = out.update
    metadesc = out.metadesc
    url = out.url
    return render_template("collection.html", oid=oid, filename=filename, title=title, article=article, update=update, url=url, metadesc=metadesc)

@app.route("/view/<id>")
def view(id):
    """ disini data dipanggil dari database """
    out = fs.get(ObjectId(id))
    pdf = out.read()
    filename = out.filename
    
    #return render_pdf(HTML(string=thefile))
    response = make_response(pdf)
    response.headers['Content-Disposition'] = "inline; filename='"+filename+".pdf'"
    response.mimetype = 'application/pdf'
    return response


@app.route("/sitemap/<n>")
def sitemap(n):
    start = (int(n) * 50000) - 50000
    end = (int(n) * 50000)
    data = db.fs.files.find()[start:end]
    sitemap_xml = render_template("sitemap.xml", data=data)
    response = make_response(sitemap_xml)
    response.headers['Content-Type'] = 'application/xml'
    return response

@app.route('/recent.atom')
def recent_feed():
    # http://werkzeug.pocoo.org/docs/contrib/atom/ 
    # wajibun: id(link) dan updated
    # feed = AtomFeed('Recent Articles',
    #                feed_url = request.url, url=request.url_root)
    # data = datas
    # for d in data:
    #    feed.add(d['nama'], content_type='html', id=d['id'], updated=datetime.datetime.now())
    # return feed.get_response()
    pass
