import subprocess

from compressor.exceptions import FilterError
from compressor.filters import CompilerFilter
from compressor.js import JsCompressor
from compressor.utils.stringformat import FormattableString as fstr
from django.conf import settings
from django.utils.safestring import mark_safe


# For use with node.js' uglifyjs minifier
class UglifySourcemapFilter(CompilerFilter):
    command = (
        "uglifyjs {infiles} -o {outfile} --source-map {mapfile}"
        " --source-map-url {mapurl} --source-map-root {maproot} -c -m")

    def input(self, **kwargs):
        return self.content

    def output(self, **kwargs):
        options = dict(self.options)
        options['outfile'] = kwargs['outfile']

        infiles = []
        for infile in kwargs['content_meta']:
            # type, full_filename, relative_filename
            infiles.append(infile[2])

        options['infiles'] = ' '.join(f for f in infiles)

        options['mapfile'] = kwargs['outfile'].replace('.js', '.map.js')

        options['mapurl'] = '{}{}'.format(
            settings.STATIC_URL, options['mapfile'])

        options['maproot'] = settings.STATIC_URL

        self.cwd = kwargs['root_location']

        try:
            command = fstr(self.command).format(**options)

            proc = subprocess.Popen(
                command, shell=True, cwd=self.cwd, stdout=self.stdout,
                stdin=self.stdin, stderr=self.stderr)
            err = proc.communicate()
        except (IOError, OSError), e:
            raise FilterError('Unable to apply %s (%r): %s' %
                              (self.__class__.__name__, self.command, e))
        else:
            if proc.wait() != 0:
                if not err:
                    err = ('Unable to apply %s (%s)' %
                           (self.__class__.__name__, self.command))
                raise FilterError(err)
            if self.verbose:
                self.logger.debug(err)


class JsUglifySourcemapCompressor(JsCompressor):

    def output(self, mode='file', forced=False):
        content = self.filter_input(forced)
        if not content:
            return ''

        concatenated_content = '\n'.join(
            c.encode(self.charset) for c in content)

        if settings.COMPRESS_ENABLED or forced:
            filepath = self.get_filepath(concatenated_content, basename=None)

            # UglifySourcemapFilter writes the file directly, as it needs to
            # output the sourcemap as well
            UglifySourcemapFilter(content).output(
                outfile=filepath,
                content_meta=self.split_content,
                root_location=self.storage.base_location)

            return self.output_file(mode, filepath)
        else:
            return concatenated_content

    def output_file(self, mode, new_filepath):
        """
        The output method that saves the content to a file and renders
        the appropriate template with the file's URL.
        """
        url = mark_safe(self.storage.url(new_filepath))
        return self.render_output(mode, {"url": url})
