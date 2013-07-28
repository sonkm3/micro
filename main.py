# -*- coding: utf-8 -*-
from google.appengine.ext import webapp, db
from google.appengine.api import users, memcache
from google.appengine.ext.webapp import util

from django.utils import simplejson as json

import time, random

class Node(db.Model):
    # path is identifier on this, so path must be uniq. but datastore can't do that. so it could be trouble in some condition.
    path = db.StringProperty()
    text = db.TextProperty()
    content_type = db.StringProperty()
    file_blob = db.BlobProperty()
    created_at = db.DateTimeProperty(auto_now_add=True)
    updated_at = db.DateTimeProperty(auto_now_add=True, auto_now=True)

    @classmethod
    def update_by_path(cls, path, text=None, content_type=None, file_blob=None):
        node = cls.get_by_path(path)
        if node == None:
            node = cls()
            node.path = path

        node.content_type = content_type
        node.text = text
        node.file_blob = file_blob
        node.put()

        memcache.add(cls.get_cache_key(path), node)

        return node

    @classmethod
    def get_by_path(cls, path):
        cache = memcache.get(cls.get_cache_key(path))
        if cache:
            return cache

        q = db.Query(cls)
        q.filter('path =', str(path))
        node = q.get()

        cache = memcache.add(cls.get_cache_key(path), node)

        return node

    @classmethod
    def delete_by_path(cls, path):
        node = cls.get_by_path(path = path)
        node.delete()

        memcache.delete(cls.get_cache_key(path))

    @staticmethod
    def get_cache_key(path):
        return 'path:' + path

class NodeHandler(webapp.RequestHandler):
    def get(self):
        node = Node.get_by_path(self.request.path)
        if node:
            self.response.headers["Content-Type"] = node.content_type
            if node.file_blob:
                self.response.out.write(node.file_blob)
            elif node.text:
                self.response.out.write(node.text)
        else:
            self.error(404)
            self.response.out.write('notfound')

class NodeAdminHandler(webapp.RequestHandler):
    @util.login_required
    def get(self):
        path = self.request.path[len('/admin/'):]
        if path == 'logout':
            return self._logout()

        if users.is_current_user_admin():
            if path == 'json':
                return self._get_json()
            if path == 'edit':
                return self._get_edit()
            else:
                return self._get_index()
        else:
            self.error(403)
            self.response.out.write('not authorized')

    def _get_json(self):
        node = Node.get_by_path(self.request.get('path'))
        if node:
            self.response.out.write(json.dumps({'path': node.path, 'text': node.text, 'content_type': node.content_type}, ensure_ascii=False))
        else:
            self.error(404)
        return

    def _get_index(self):
        html_tmpl = """<html><head><title>micro</title></head><body>
        <h2><a href='/admin/edit'>create</a></h2>
        <h2>list</h2>
        <ul>
        %s
        </ul>
        <h2><a href='/admin/logout'>logout</a></h2>
        </body></html>
        """

        list_html_lines = []
        nodes = Node.all().order('path')
        for node in nodes:
            list_html_lines.append("<li><a href='%s'>%s</a></li>" % ('/admin/edit?path=' + node.path, node.path))

        html = html_tmpl % (''.join(list_html_lines))

        self.response.out.write(html)

    def _get_edit(self):
        html = """<html>
        <head><title>micro</title>
        <script src='http://ajax.googleapis.com/ajax/libs/jquery/1.7.1/jquery.min.js'></script>
        <script>
        function get_path(){
            var query_list = window.location.href.slice(window.location.href.indexOf('?') + 1).split('&')
            var path = '';
            for(var i =0; i < query_list.length; i++){
                query = query_list[i].split('=');
                if(query[0] == 'path'){
                    path = query[1];
                    break;
                }
            }
            return path
        }
        function load_node(path){
            $.getJSON(
                '/admin/json',
                {path: path},
                function(data){
                    $('#path').val(data['path'])
                    $('#text').val(data['text'])
                    $('#content_type').val(data['content_type'])
                }
            );
        }
        $(document).ready(function(){
            var overwrite = true;
            var path = get_path();
            if(path != ''){
                load_node(path);
            }else{
                $('#path').val('/')
                $('#content_type').val('text/html; charset=utf-8')
                $('#delete').remove();
                overwrite = true;
            }
            $('#back').click(function(){$(location).attr('href',"/admin/");});
            $('#delete').click(function(){return confirm('delete?')});
            $('#update').click(function(){if(overwrite == true){return confirm('overwrite?')}});
            $('#path').change(function(){
                overwrite = false;
                $.getJSON(
                    '/admin/json',
                    {path: $('#path').val()},
                    function(data){
                        if(data.path == $('#path').val()){overwrite = true;}
                    }
                );                    
            })
            if($("#image").attr('src')){$("#text").remove();$("#text_label").remove()}
        });
        </script>
        <style>
        #path{width: 500px;}
        #text{width: 500px; height: 300px;}
        </style>
        </head><body>
        <form id='form' method='post' action='update' enctype="multipart/form-data">
        <label id="path_label">path</label><br/><input id='path' name='path'/ value=""><br/>
        <label id="text_label">html</label><br/><textarea id='text' name='text'></textarea><br/>
        <label id="file_label">file</label><br/><input type='file' name='file' id='file'/><br/>
        %s<br/>
        <label id="type_label">type</label><br/><input id='content_type' name='content_type'/ value=""><br/>
        <input type='hidden' name='csrf_key' value='%s' id='csrf'/>
        <input type='submit' name='update' value='update' id='update'/>
        <input type='submit' name='delete' value='delete' id='delete'/>
        <input type='button' name='back' value='back' id='back'/>
        </form>
        </body></html>
        """

        csrf_key = self._generate_csrf_key()

        image_html = ''
        if self.request.get('path'):
            node = Node.get_by_path(self.request.get('path'))
            if node.file_blob and node.content_type[0:len('image')] == 'image':
                image_html = '<img id="image" src="' + node.path + '"/>'

        self.response.out.write(html%(image_html, csrf_key))

    def _logout(self):
        self.redirect(users.create_logout_url('/admin/'))

    def post(self):
        if users.is_current_user_admin():
            if not self._check_csrf_key(self.request.get('csrf_key')):
                return self.redirect('/admin/')

            path = self.request.path[len('/admin/'):]
            if path == 'update':
                return self._post_update()
            else:
                return self.redirect('/admin/')

    def _post_update(self):
        if self.request.get('delete'):
            Node.delete_by_path(path = self.request.get('path'))
        else:
            content_type = self.request.get('content_type')
            file_blob = None
            if self.request.get('file_blob'):
                content_type = self.request.body_file.vars['file'].headers['content-type']
                file_blob = db.Blob(str(self.request.get('file')))
            node = Node.update_by_path(path = self.request.get('path'), text = self.request.get('text'), file = file, content_type=content_type)
        self.redirect('/admin/edit?path=' + node.path)

    @staticmethod
    def _generate_csrf_key():
        csrf_key = str(time.time())+'/'+str(random.randint(0,1000000))
        memcache.add(csrf_key, True, 3600)
        return csrf_key

    @staticmethod
    def _check_csrf_key(csrf_key):
        if memcache.get(csrf_key) == True:
            return True
        return False

def main():
    application = webapp.WSGIApplication([
                                            ('/admin/.*', NodeAdminHandler),
                                            ('/.*', NodeHandler),
                                         ],
                                         debug=True)
    util.run_wsgi_app(application)


if __name__ == '__main__':
    main()
