# Copyright 2017 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Cloud Function (nicely deployed in deployment) DM template."""

import base64
import hashlib
import zipfile
from StringIO import StringIO


def GenerateConfig(ctx):
    """Generate YAML resource configuration."""
    in_memory_output_file = StringIO()
    function_name = ctx.env['deployment'] + '-' + ctx.properties['functionName']
    zip_file = zipfile.ZipFile(
        in_memory_output_file, mode='w', compression=zipfile.ZIP_DEFLATED)
    for imp in ctx.imports:
        if imp.startswith(ctx.properties['codeLocation']):
            zip_file.writestr(imp[len(ctx.properties['codeLocation']):],
                              ctx.imports[imp])
    zip_file.close()
    content = base64.b64encode(in_memory_output_file.getvalue())
    m = hashlib.md5()
    m.update(content)
    bucket_name = ctx.env['project'] + '-' + ctx.properties['codeBucket']
    source_archive_url = 'gs://%s/%s' % (bucket_name,
                                         m.hexdigest() + '.zip')
    cmd = "echo '%s' | base64 -d > /function/function.zip;" % (content)
    volumes = [{'name': 'function-code', 'path': '/function'}]
    create_staging_bucket = {
        'name': bucket_name,
        'type': 'gcp-types/storage-v1:buckets',
        'properties': {
            'predefinedAcl': 'projectPrivate',
            'projection': 'full',
            'location': ctx.properties['location'],
            'storageClass': 'STANDARD'
        }
    }
    build_step = {
        'name': 'upload-function-code',
        'action': 'gcp-types/cloudbuild-v1:cloudbuild.projects.builds.create',
        'metadata': {
            'runtimePolicy': ['UPDATE_ON_CHANGE']
        },
        'properties': {
            'steps': [{
                'name': 'ubuntu',
                'args': ['bash', '-c', cmd],
                'volumes': volumes,
            }, {
                'name': 'gcr.io/cloud-builders/gsutil',
                'args': ['cp', '/function/function.zip', source_archive_url],
                'volumes': volumes
            }],
            'timeout':
                '120s'
        }
    }
    cloud_function = {
        'type': 'gcp-types/cloudfunctions-v1:projects.locations.functions',
        'name': function_name,
        'properties': {
            'parent':
                '/'.join([
                    'projects', ctx.env['project'], 'locations', ctx.properties['location']
                ]),
            'function':
                function_name,
            'labels': {
                # Add the hash of the contents to trigger an update if the bucket
                # object changes
                'content-md5': m.hexdigest()
            },
            'sourceArchiveUrl':
                source_archive_url,
            'environmentVariables': {
                'codeHash': m.hexdigest(),
                'gitCredentialBucket': ctx.env['project'] + '-' + ctx.properties['gitCredentialBucket'],
                'codeBucket': ctx.properties['codeBucket'],
                'deployKey': ctx.properties['deployKey'],
                'keyRing': ctx.properties['keyRing']
            },
            'entryPoint':
                ctx.properties['entryPoint'],
            'httpsTrigger': {},
            'timeout':
                ctx.properties['timeout'],
            'availableMemoryMb':
                ctx.properties['availableMemoryMb'],
            'runtime':
                ctx.properties['runtime']
        },
        'metadata': {
            'dependsOn': ['upload-function-code']
        }
    }
    resources = [create_staging_bucket, build_step, cloud_function]

    return {
        'resources': resources
    }
