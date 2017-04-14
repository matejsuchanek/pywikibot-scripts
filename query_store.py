# -*- coding: utf-8 -*-

class QueryStore(object):

    '''Interface for loading SPARQL queries from text files'''

    def __init__(self, path='scripts\\myscripts\\queries'):
        self.path = path

    def get_query(self, name):
        with open('%s\\%s.txt' % (self.path, name), 'r') as file:
            file.seek(0)
            return file.read()

    def build_query(self, name, **params):
        return self.get_query(name) % params
