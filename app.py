import os
from os.path import dirname, exists, isdir, join, splitext
from uuid import uuid4
import base64
import hmac
import hashlib
import json
import boto3
from boto3.s3.transfer import S3Transfer

import tornado.ioloop
import tornado.web

TMP_STORAGE_PATH = "/tmp"
METADATA_FILE_NAME = "meta.json"
BUCKET = 'sm-engine-upload'

s3transfer = S3Transfer(boto3.client('s3', os.getenv('AWS_REGION')))


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.set_cookie('session_id', str(uuid4()))
        self.render('static/index.html')


def new_json_file(session_id):
    dir_path = get_dataset_path(session_id)
    file_path = join(dir_path, METADATA_FILE_NAME)
    if exists(file_path):
        raise RuntimeError("JSON already exists: {}".format(file_path))
    return open(file_path, 'wb')


def get_dataset_path(session_id):
    return join(TMP_STORAGE_PATH, session_id)


def prepare_directory(session_id):
    dir_path = get_dataset_path(session_id)
    if not isdir(dir_path):
        os.mkdir(dir_path)


class SubmitHandler(tornado.web.RequestHandler):

    def post(self):
        if self.request.headers["Content-Type"].startswith("application/json"):
            data = self.request.body
            session_id = self.get_cookie('session_id')
            prepare_directory(session_id)
            with new_json_file(session_id) as fp:
                fp.write(data)

            local = join(get_dataset_path(session_id), METADATA_FILE_NAME)
            # meta_json = json.loads(data)
            # user_email = meta_json['Submitted_By']['Submitter']['Email']
            # ds_name = meta_json['']
            # s3key = join(user_email, ds_name, session_id, METADATA_FILE_NAME)
            s3key = join(session_id, METADATA_FILE_NAME)
            s3transfer.upload_file(filename=local, bucket=BUCKET, key=s3key)

            self.set_header("Content-Type", "text/plain")
            self.write("Uploaded to S3: {}".format(data))
        else:
            print(self.request.headers["Content-Type"])
            self.write("Error: Content-Type has to be 'application/json'")


class UploadHandler(tornado.web.RequestHandler):
    AWS_CLIENT_SECRET_KEY = os.getenv('AWS_CLIENT_SECRET_KEY')

    def sign_policy(self, policy):
        """ Sign and return the policy document for a simple upload.
        http://aws.amazon.com/articles/1434/#signyours3postform """
        signed_policy = base64.b64encode(policy)
        signature = base64.b64encode(hmac.new(
            self.AWS_CLIENT_SECRET_KEY, signed_policy, hashlib.sha1).
            digest())
        return {'policy': signed_policy, 'signature': signature}

    def sign_headers(self, headers):
        """ Sign and return the headers for a chunked upload. """
        return {
            'signature': base64.b64encode(hmac.new(
                self.AWS_CLIENT_SECRET_KEY, headers, hashlib.sha1).
                digest())
        }

    def post(self):
        """ Route for signing the policy document or REST headers. """
        request_payload = json.loads(self.request.body)
        if request_payload.get('headers'):
            response_data = self.sign_headers(request_payload['headers'])
        else:
            response_data = self.sign_policy(self.request.body)
        return self.write(response_data)


def make_app():
    return tornado.web.Application([
        (r"/", MainHandler),
        (r"/submit", SubmitHandler),
        (r'/s3/sign', UploadHandler)
    ],
        static_path=join(dirname(__file__), "static"),
        static_url_prefix='/static/',
        debug=True,
        compress_response=True
    )


if __name__ == "__main__":
    if not isdir(TMP_STORAGE_PATH):
        os.mkdir(TMP_STORAGE_PATH)
    app = make_app()
    app.listen(9777)
    tornado.ioloop.IOLoop.current().start()
