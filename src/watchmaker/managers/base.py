# -*- coding: utf-8 -*-
import abc
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
import zipfile

from six.moves import urllib

from watchmaker.exceptions import WatchmakerException


class ManagerBase(object):
    """
    Base class for operating system managers.

    All child classes will have access to methods unless overridden by
    similarly-named method in the child class.
    """
    boto3 = None
    boto_client = None

    def __init__(self):
        self.log = logging.getLogger(
            '{0}.{1}'.format(__name__, self.__class__.__name__)
        )
        self.working_dir = None
        return

    def _import_boto3(self):
        if self.boto3:
            return

        self.log.info("Dynamically importing boto3 ...")
        try:
            self.boto3 = __import__("boto3")
            self.boto_client = __import__(
                "botocore.client",
                globals(),
                locals(),
                ["ClientError"],
                -1
            )
        except ImportError:
            msg = 'Unable to import boto3 module.'
            self.log.critical(msg)
            raise

    def _get_s3_file(self, url, bucket_name, key_name, destination):
        self._import_boto3()

        try:
            s3 = self.boto3.resource("s3")
            s3.meta.client.head_bucket(Bucket=bucket_name)
            s3.Object(bucket_name, key_name).download_file(destination)
        except self.boto_client.ClientError:
            msg = 'Bucket does not exist.  bucket = {0}.'.format(bucket_name)
            self.log.critical(msg)
            raise
        except Exception:
            msg = (
                'Unable to download file from S3 bucket. url = {0}. '
                'bucket = {1}. key = {2}. file = {3}.'
                .format(url, bucket_name, key_name, destination)
            )
            self.log.critical(msg)
            raise

    def download_file(self, url, filename, sourceiss3bucket=False):
        self.log.debug('Downloading: {0}'.format(url))
        self.log.debug('Destination: {0}'.format(filename))
        self.log.debug('S3: {0}'.format(sourceiss3bucket))

        # TODO Rework this to properly reflect logic flow cleanly.
        if sourceiss3bucket:
            self._import_boto3()

            bucket_name = url.split('/')[3]
            key_name = '/'.join(url.split('/')[4:])

            self.log.debug('Bucket Name: {0}'.format(bucket_name))
            self.log.debug('key_name: {0}'.format(key_name))

            try:
                s3 = self.boto3.resource('s3')
                s3.meta.client.head_bucket(Bucket=bucket_name)
                s3.Object(bucket_name, key_name).download_file(filename)
            except (NameError, self.boto_client.ClientError):
                self.log.error(
                    'NameError: {0}'.format(self.boto_client.ClientError)
                )
                try:
                    bucket_name = url.split('/')[2].split('.')[0]
                    key_name = '/'.join(url.split('/')[3:])
                    s3 = self.boto3.resource("s3")
                    s3.meta.client.head_bucket(Bucket=bucket_name)
                    s3.Object(bucket_name, key_name).download_file(filename)
                except Exception as exc:
                    msg = (
                        'Unable to download file from S3 bucket. url = {0}. '
                        'bucket = {1}. key = {2}. file = {3}.'
                        .format(url, bucket_name, key_name, filename)
                    )
                    self.log.critical(msg)
                    raise
            except Exception:
                msg = (
                    'Unable to download file from S3 bucket. url = {0}. '
                    'bucket = {1}. key = {2}. file = {3}.'
                    .format(url, bucket_name, key_name, filename)
                )
                self.log.critical(msg)
                raise
            self.log.info(
                'Downloaded file from S3 bucket  --  url = {0}.  '
                'filename = {1}'.format(url, filename)
            )
        else:
            try:
                response = urllib.request.urlopen(url)
                with open(filename, 'wb') as outfile:
                    shutil.copyfileobj(response, outfile)
            except Exception:
                msg = (
                    'Unable to download file from web server. url = {0}. '
                    'filename = {1}.'
                    .format(url, filename)
                )
                self.log.critical(msg)
                raise
            self.log.info(
                'Downloaded file from web server  --  url = {0}.  '
                'filename = {1}'.format(url, filename)
            )

    def create_working_dir(self, basedir, prefix):
        """
        Create a directory in `basedir` with a prefix of `prefix`.

        Args:
            prefix (str):
                Prefix to prepend to the working directory
            basedir (str):
                The directory in which to create the working directory
        """
        self.log.info('Creating a working directory.')
        original_umask = os.umask(0)
        try:
            working_dir = tempfile.mkdtemp(prefix=prefix, dir=basedir)
        except Exception:
            msg = (
                'Could not create a working dir in {0}.  Exception: {1}'
                .format(basedir)
            )
            self.log.critical(msg)
            raise
        self.log.debug('Working directory: {0}'.format(working_dir))
        self.working_dir = working_dir
        os.umask(original_umask)

    def call_process(self, cmd):
        if not isinstance(cmd, list):
            msg = 'Command is not a list: {0}'.format(str(cmd))
            self.log.critical(msg)
            raise WatchmakerException(msg)
        rsp = subprocess.call(cmd)

        if rsp != 0:
            msg = 'Command failed: {0}'.format(str(cmd))
            self.log.critical(msg)
            raise WatchmakerException(msg)

    def cleanup(self):
        self.log.info('Cleanup Time...')
        try:
            self.log.debug('{0} being cleaned up.'.format(self.working_dir))
            shutil.rmtree(self.working_dir)
        except Exception as exc:
            msg = 'Cleanup Failed!'
            self.log.critical(msg)
            raise

        self.log.info(
            'Removed temporary data in working directory -- {0}'
            .format(self.working_dir)
        )
        self.log.info('Exiting cleanup routine...')

    def extract_contents(self, filepath, to_directory, create_dir=False):
        """
        Extracts a compressed file to the specified directory.
        Supports files that end in .zip, .tar.gz, .tgz, tar.bz2, or tbz.

        Args:
            filepath (str):
                Path to the compressed file
            to_directory (str):
                Path to the target directory
            create_dir (bool):
                If true, create subdirectory within to_directory
                that represents original path of compressed file
        """
        if filepath.endswith('.zip'):
            self.log.debug('File Type: zip')
            opener, mode = zipfile.ZipFile, 'r'
        elif filepath.endswith('.tar.gz') or filepath.endswith('.tgz'):
            self.log.debug('File Type: GZip Tar')
            opener, mode = tarfile.open, 'r:gz'
        elif filepath.endswith('.tar.bz2') or filepath.endswith('.tbz'):
            self.log.debug('File Type: Bzip Tar')
            opener, mode = tarfile.open, 'r:bz2'
        else:
            msg = (
                'Could not extract "{0}" as no appropriate extractor is found.'
                .format(filepath)
            )
            self.log.critical(msg)
            raise WatchmakerException(msg)

        if create_dir:
            to_directory = os.sep.join((
                to_directory,
                '.'.join(filepath.split(os.sep)[-1].split('.')[:-1])
            ))

        try:
            os.makedirs(to_directory)
        except OSError:
            if not os.path.isdir(to_directory):
                msg = 'Unable create directory - {0}'.format(to_directory)
                self.log.critical(msg)
                raise

        cwd = os.getcwd()
        os.chdir(to_directory)

        try:
            openfile = opener(filepath, mode)
            try:
                openfile.extractall()
            finally:
                openfile.close()
        finally:
            os.chdir(cwd)

        self.log.info(
            'Extracted file  --  source = {0}  dest   = {1}'
            .format(filepath, to_directory)
        )


class LinuxManager(ManagerBase):
    """
    Base class for Linux Managers.

    Serves as a foundational class to keep OS consitency.
    """

    def __init__(self):
        super(LinuxManager, self).__init__()

    def _install_from_yum(self, packages):
        yum_cmd = ['sudo', 'yum', '-y', 'install']
        if isinstance(packages, list):
            yum_cmd.extend(packages)
        else:
            yum_cmd.append(packages)
        rsp = subprocess.call(yum_cmd)
        self.log.debug(packages)
        self.log.debug('Return code of yum install: {0}'.format(rsp))

        if rsp != 0:
            msg = 'Installing Salt from Yum has failed!'
            self.log.critical(msg)
            raise WatchmakerException(msg)


class WindowsManager(ManagerBase):
    """

    """

    def __init__(self):
        super(WindowsManager, self).__init__()


class WorkersManagerBase(object):
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def _worker_execution(self):
        return

    @abc.abstractmethod
    def _worker_validation(self):
        return

    @abc.abstractmethod
    def worker_cadence(self):
        return

    @abc.abstractmethod
    def cleanup(self):
        return
