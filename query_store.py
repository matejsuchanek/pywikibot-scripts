# -*- coding: utf-8 -*-
import os

class QueryStore(object):

    '''Interface for loading SPARQL queries from text files'''

    def __init__(self, path=None):
        if path is None:
            dirname = os.path.dirname(os.path.realpath(__file__))
            path = os.join.path(dirname, 'queries')
        self.path = path

    def get_query(self, name):
        with open('%s.txt' % os.path.join(self.path, name), 'r',
                  encoding='utf-8') as file:
            file.seek(0)
            return file.read()

    def build_query(self, name, **params):
        return self.get_query(name) % params

if __name__ == '__main__':
    print('This script is not runnable from command line.')
