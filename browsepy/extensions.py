import re

import jinja2
import jinja2.ext
import jinja2.lexer


class StateMachineCompressContext(object):
    '''
    Base non-compressing implementation for state-machine-based compression
    contexts compatible with :class:`CompressExtension`.
    '''
    re_whitespace = re.compile('[ \\t\\r\\n]+')
    token_class = jinja2.lexer.Token
    block_tokens = {
        'variable_begin': 'variable_end',
        'block_begin': 'block_end'
        }
    jumps = {}  # character-based state machine jumps
    current = None  # current state
    start = ''  # character which started current state
    pending = ''  # buffer of current state data
    lineno = 0  # current token lineno
    skip_until_token = None  # inside token until this is met

    def _minify(self, data, current, start, partial=False):
        return data

    def _options(self, value, current, start):
        offset = len(start)
        for mark, next in self.jumps[current].items():
            index = value.find(mark, offset)
            if -1 != index:
                yield index, mark, next
        yield len(value), '', None  # avoid value errors on empty min()

    def feed(self, token):
        if self.skip_until_token:
            yield token
            if token.type == self.skip_until_token:
                self.skip_until_token = None
            return

        if token.type in self.block_tokens:
            for data in self.finalize():
                yield data
            yield token
            self.skip_until_token = self.block_tokens[token.type]
            return

        size = len(token.value)
        lineno = token.lineno
        self.pending += token.value
        while True:
            index, mark, next = min(
                self._options(self.pending, self.current, self.start),
                key=lambda x: (x[0], -len(x[1]))
                )
            if next is None:
                break
            data = self._minify(self.pending[:index], self.current, self.start)
            self.lineno = lineno if size > len(self.pending) else self.lineno
            self.start = mark
            self.current = next
            self.pending = self.pending[index:]
            yield self.token_class(self.lineno, 'data', data)

    def finalize(self):
        if self.pending:
            data = self._minify(self.pending, self.current, self.start, True)
            yield self.token_class(self.lineno, 'data', data)
        self.start = ''
        self.pending = ''


class SGMLCompressContext(StateMachineCompressContext):
    block_tags = {}  # block content will be treated as literal text
    jumps = {  # state machine jumps
        'text': {
            '<': 'tag',
            '<!--': 'comment',
            '<![CDATA[': 'cdata',
            },
        'lit1': {'"': 'tag'},
        'lit2': ("'", 'tag'),
        'tag': {
            '>': 'text',
            '"': 'lit1',
            "'": 'lit2'
            },
        'comment': {'-->': 'text'},
        'cdata': {']]>': 'text'}
        }
    current = 'text'
    skip_until = None  # inside literal tag until this is met

    def _minify(self, data, current, start, partial=False):
        if current == 'tag':
            tagstart = start == '<'
            data = self.re_whitespace.sub(' ', data[1:] if tagstart else data)
            if tagstart:
                data = data.lstrip() if partial else data.strip()
                tagname = data.split(' ', 1)[0]
                self.skip_until = self.block_tags.get(tagname)
                return '<' + data
            elif partial:
                return data.rstrip()
            return start if data.strip() == start else data
        elif current == 'text':
            if not self.skip_until:
                return start if data.strip() == start else data
            elif not partial:
                self.skip_until = None
            return data
        return data

    def _options(self, value, current, start):
        offset = len(start)
        if self.skip_until and current == 'text':
            mark = self.skip_until
            index = value.find(mark, offset)
            if -1 != index:
                yield index, mark, current
        else:
            supa = super(SGMLCompressContext, self)
            for option in supa._options(value, current, start):
                yield option
        yield len(value), '', None  # avoid value errors on empty min()


class HTMLCompressContext(SGMLCompressContext):
    block_tags = {
        'textarea': '</textarea>',
        'pre': '</pre>',
        'script': '</script>',
        'style': '</style>',
        }


class JSONCompressContext(StateMachineCompressContext):
    jumps = {
        'object': {
            '"': 'string'
            },
        'string': {
            '"': 'object',
            '\\': 'escape'
            }
        }
    current = 'object'

    def _minify(self, data, current, start, partial=False):
        return data.replace(' ', '') if current == 'object' else data

    def _options(self, value, current, start):
        if current == 'escape':
            if value:
                yield 0, value[0], current
        else:
            supa = super(SGMLCompressContext, self)
            for option in supa._options(value, current, start):
                yield option
        yield len(value), '', None  # avoid value errors on empty min()


class CompressExtension(jinja2.ext.Extension):
    context_class = StateMachineCompressContext
    extensions = {}

    def supported(self, filename):
        print(filename or 'SIN FILENAME')
        return filename and filename.rsplit('.', 1)[-1] in self.extensions

    def supported_filter_stream(self, stream):
        feed = self.context_class()
        for token in stream:
            for data in feed.feed(token):
                yield data
        for data in feed.finalize():
            yield data

    def filter_stream(self, stream):
        if self.supported(stream.filename):
            return self.supported_filter_stream(stream)
        return stream


class HTMLCompress(CompressExtension):
    context_class = HTMLCompressContext
    extensions = {'html', 'xml'}


class JSONCompress(CompressExtension):
    context_class = JSONCompressContext
    extensions = {'json'}
