#!/usr/bin/env python


#sudo apt-get install python3-bs4

import os
import re
import sys
import time
import json
import shutil
import zipfile
import tempfile
import subprocess
import collections
import urllib.request
import distutils.version
from urllib.parse import unquote
import hashlib
from pathlib import Path

from PIL import Image
from bs4 import BeautifulSoup
        
# You can adjust some setting here. Default is for QOwnNotes app.

## Select meta data options
meta_data_in_yaml = True  # True a YAML front matter block will contain the following meta data items.  
                           # False any selected meta data options below will be in the md text
insert_title = True  # True will add the title of the note as a field in the YAML block, False no title in block.
insert_ctime = True  # True to insert note creation time in the YAML block, False to disable.
insert_mtime = True  # True to insert note modification time in the YAML block, False to disable.
tags = True  # True to insert list of tags, False to disable
tag_prepend = ''  # string to prepend each tag in a tag list inside the note, default is empty
tag_delimiter = ', '  # string to delimit tags, default is comma separated list
no_spaces_in_tags = False  # True to replace spaces in tag names with '_', False to keep spaces

## Select file link options
links_as_URI = False  # True for file://link%20target style links, False for /link target style links
absolute_links = False  # True for absolute links, False for relative links

## Select File/Attachments/Media options
media_dir_name = '_resources'  # name of the directory inside the produced directory where all images and attachments will be stored
md_file_ext = 'md'  # extension for produced markdown syntax note files
creation_date_in_filename = False  # True to insert note creation time to the note file name, False to disable.

############################################################################

Notebook = collections.namedtuple('Notebook', ['path', 'media_path'])


def sanitise_path_string(path_str):
    for char in (':', '/', '\\', '|'):
        path_str = path_str.replace(char, '-')
    for char in ('?', '*'):
        path_str = path_str.replace(char, '')
    path_str = path_str.replace('<', '(')
    path_str = path_str.replace('>', ')')
    path_str = path_str.replace('"', "'")
    path_str = urllib.parse.unquote(path_str)

    return path_str[:100]


def create_yaml_meta_block():
    yaml_block = '---\n'

    if insert_title:
        yaml_block = '{}title: "{}"\n'.format(yaml_block,  re.sub(r'(["\\])', r'\\\1', note_title))

    if insert_mtime and note_mtime:
        yaml_text_mtime = time.strftime('%Y-%m-%d %H:%M:%SZ', time.localtime(note_mtime))
        yaml_block = '{}updated: "{}"\n'.format(yaml_block, yaml_text_mtime)

    if insert_ctime and note_ctime:
        yaml_text_ctime = time.strftime('%Y-%m-%d %H:%M:%SZ', time.localtime(note_ctime))
        yaml_block = '{}created: "{}"\n'.format(yaml_block, yaml_text_ctime)

    if tags and note_data.get('tag', ''):
        if no_spaces_in_tags:
            note_data['tag'] = [tag.replace(' ', '_') for tag in note_data['tag']]
        yaml_tag_list = tag_delimiter.join(''.join((tag_prepend, tag)) for tag in note_data['tag'])
        yaml_block = '{}Tags: [{}]\n'.format(yaml_block, yaml_tag_list)

    yaml_block = '{}---\n'.format(yaml_block)
    
    if attachment_list:
        yaml_block = '{}\nAttachments:  {}\n'.format(yaml_block, ', '.join(attachment_list))
    
    return yaml_block


def create_text_meta_block():
    text_block = ''
    
    insert_mtime = False
    if insert_mtime and note_mtime:
        text_mtime = time.strftime('%Y-%m-%d %H:%M:%SZ', time.localtime(note_mtime))
        text_block = 'Modified: {}  \n{}'.format(text_mtime, text_block)
        
    insert_ctime = True
    if insert_ctime and note_ctime:
        text_ctime = time.strftime('%Y-%m-%d %H:%M:%SZ', time.localtime(note_ctime))
        text_block = '**Created: {}**\n{}'.format(text_ctime, text_block)
        
    if attachment_list:
        text_block = 'Attachments: {}  \n{}'.format(', '.join(attachment_list), text_block)
        
    if note_data.get('tag', '') and tags:
        if no_spaces_in_tags:
            note_data['tag'] = [tag.replace(' ', '_') for tag in note_data['tag']]
        tag_list = tag_delimiter.join(''.join((tag_prepend, tag)) for tag in note_data['tag'])
        text_block = 'Tags: {}  \n{}'.format(tag_list, text_block)
    
    insert_title = False
    if insert_title:
        text_block = '{}\n{}\n{}'.format(note_title, '=' * len(note_title), text_block)
    
    return text_block


work_path = Path.cwd()
media_dir_name = sanitise_path_string(media_dir_name)
pandoc_input_file = tempfile.NamedTemporaryFile(delete=False)
pandoc_output_file = tempfile.NamedTemporaryFile(delete=False)


if not shutil.which('pandoc') and not os.path.isfile('pandoc'):
    print('Can\'t find pandoc. Please install pandoc or place it to the directory, where the script is.')
    exit(1)

try:
    pandoc_ver = subprocess.check_output(['pandoc', '-v'], timeout=3).decode('utf-8')[7:].split('\n', 1)[0].strip()
    print('Found pandoc ' + pandoc_ver)

    if distutils.version.LooseVersion(pandoc_ver) < distutils.version.LooseVersion('1.16'):
        pandoc_args = ['pandoc', '-f', 'html', '-t', 'markdown_strict+pipe_tables-raw_html',
                       '--no-wrap', '-o', pandoc_output_file.name, pandoc_input_file.name]
    elif distutils.version.LooseVersion(pandoc_ver) < distutils.version.LooseVersion('1.19'):
        pandoc_args = ['pandoc', '-f', 'html', '-t', 'markdown_strict+pipe_tables-raw_html',
                       '--wrap=none', '-o', pandoc_output_file.name, pandoc_input_file.name]
    elif distutils.version.LooseVersion(pandoc_ver) < distutils.version.LooseVersion('2.11.2'):
        pandoc_args = ['pandoc', '-f', 'html', '-t', 'markdown+pipe_tables-raw_html',
                       '--wrap=none', '--atx-headers', '-o',
                       pandoc_output_file.name, pandoc_input_file.name]
    else:
        pandoc_args = ['pandoc', '-f', 'html', '-t', 'markdown_strict+pipe_tables-raw_html',
                       '--wrap=none', '--markdown-headings=atx', '-o',
                       pandoc_output_file.name, pandoc_input_file.name]
except Exception:
    pandoc_args = ['pandoc', '-f', 'html', '-t', 'markdown_strict+pipe_tables-raw_html',
                   '--wrap=none', '--markdown-headings=atx', '-o',
                   pandoc_output_file.name, pandoc_input_file.name]

if len(sys.argv) > 1:
    files_to_convert = [Path(path) for path in sys.argv[1:]]
else:
    files_to_convert = Path(work_path).glob('*.nsx')

if not files_to_convert:
    print('No .nsx files found')
    exit(1)

for file in files_to_convert:
    nsx_file = zipfile.ZipFile(str(file))
    config_data = json.loads(nsx_file.read('config.json').decode('utf-8'))
    notebook_id_to_path_index = {}

    recycle_bin_path = work_path / Path('Recycle bin')

    n = 1
    while recycle_bin_path.is_dir():
        recycle_bin_path = work_path / Path('{}_{}'.format('Recycle bin', n))
        n += 1

    recycle_bin_media_path = recycle_bin_path / media_dir_name
    recycle_bin_media_path.mkdir(parents=True)
    notebook_id_to_path_index['1027_#00000000'] = Notebook(recycle_bin_path, recycle_bin_media_path)

    print('Extracting notes from "{}"'.format(file.name))

    for notebook_id in config_data['notebook']:
        notebook_data = json.loads(nsx_file.read(notebook_id).decode('utf-8'))
        notebook_title = notebook_data['title'] or 'Untitled'
        notebook_path = work_path / Path(sanitise_path_string(notebook_title))

        n = 1
        while notebook_path.is_dir():
            notebook_path = work_path / Path('{}_{}'.format(sanitise_path_string(notebook_title), n))
            n += 1

        notebook_media_path = Path(notebook_path / media_dir_name)
        notebook_media_path.mkdir(parents=True)

        notebook_id_to_path_index[notebook_id] = Notebook(notebook_path, notebook_media_path)

    note_id_to_title_index = {}
    converted_note_ids = []

    for note_id in config_data['note']:
        note_data = json.loads(nsx_file.read(note_id).decode('utf-8'))

        note_title = note_data.get('title', 'Untitled')
        note_ctime = note_data.get('ctime', '')
        note_mtime = note_data.get('mtime', '')

        note_id_to_title_index[note_id] = note_title

        try:
            parent_notebook_id = note_data['parent_id']
            parent_notebook = notebook_id_to_path_index[parent_notebook_id]
        except KeyError:
            continue

        #print("\n++++++++++++++++++++++++++++++++++++++\n")
        print('\nConverting note[{}] "{}"'.format(note_id, note_title))
        rawcontent = note_data.get('content', '')
        #print(rawcontent)
        soup = BeautifulSoup(rawcontent, 'html.parser')
        for img in soup.find_all('img'):
            if img.has_attr('class') and 'syno-notestation-image-object' in img['class'] and img.has_attr('ref'):
                img['src'] = img['ref']
                del img['ref']
                del img['class']
                #print(img)
        content = re.sub(r'<div><br/></div>|<div></div>', '', str(soup), flags=re.I)

        #print(content)
        #print("\n++++++++++++++++++\n")
        Path(pandoc_input_file.name).write_text(content, 'utf-8')
        pandoc = subprocess.Popen(pandoc_args)
        pandoc.wait(20)
        content = Path(pandoc_output_file.name).read_text('utf-8')
        content = re.sub(r'\n([^{}\n]+)\{style="font-weight: bold;"\}\n', r'\n**\1**\n', content, flags=re.I)
        content = re.sub(r'\{#?[^{^}]*style=[^}]+\}', '', content, flags=re.I)
        content = re.sub(r'\{[#\.][^{^}^#]+\}', '', content, flags=re.I)
        content = re.sub(r'\n<div>\n|\n</div>\n|\n *::: *\n|^ *::: *\n|\n\\\n', '\n\n', content, flags=re.I)
        content = re.sub(r'^<div>\n|\n<div>\n|\n</div>\n|\n</div>$|\n::: ?\n|\n\\\n', '\n\n', content, flags=re.I)
        content = re.sub(r'\{width="[0-9]+"\s+height="[0-9]+"\}', '', content, flags=re.I)
        content = re.sub(r'\n{2,}', '\n\n', content, flags=re.I)
        attachments_data = note_data.get('attachment')
        attachment_list = []

        if attachments_data:
            for attachment_id in note_data.get('attachment', ''):

                ref = note_data['attachment'][attachment_id].get('ref', '')
                ext = note_data['attachment'][attachment_id].get('ext', '')
                if ext:
                    ext = "." + ext
                md5 = note_data['attachment'][attachment_id]['md5']
                source = note_data['attachment'][attachment_id].get('source', '')
                name = sanitise_path_string(note_data['attachment'][attachment_id]['name'])
                name = name.replace('ns_attach_image_', '')
                if ext and not re.search(ext+"$", name, flags=re.I):
                    name = name + ext
                name_parts = name.rpartition('.')

                n = 1
                while Path(parent_notebook.media_path / name).is_file():
                    name = ''.join((name_parts[0], '_{}'.format(n), name_parts[1], name_parts[2]))
                    n += 1

                if links_as_URI:
                    if absolute_links:
                        link_path = Path(parent_notebook.media_path / name).as_uri()
                    else:
                        #remove file:// to be compatible with Joplin
                        link_path = '{}/{}'.format(urllib.request.pathname2url(media_dir_name),
                                                          urllib.request.pathname2url(name))
                else:
                    if absolute_links:
                        link_path = str(Path(parent_notebook.media_path / name))
                    else:
                        link_path = '{}/{}'.format(media_dir_name, name)

                try:
                    file_con =  nsx_file.read('file_' + md5)
                    if len(file_con) < 100:
                        raise Exception("{} is too small, skip it".format('file_' + md5))
                    Path(parent_notebook.media_path / name).write_bytes(file_con)
                    img=Image.open(str(parent_notebook.media_path / name))
                    img.verify()
                    hasLocalFile = True
                    attachment_link = '[{}]({})'.format(name, link_path)
                except Exception:
                    hasLocalFile = False
                    if source:
                        attachment_link = '[{}]({})'.format(name, source)
                    else:
                        print('Can\'t find attachment "{}" of note "{}" or the file is too small or format error'.format(name, note_title))
                        attachment_link = '[NOT FOUND]({})'.format(link_path)


                if ref and source:
                    if hasLocalFile:
                        content = content.replace(ref, link_path)
                    else:
                        content = content.replace(ref, source)
                elif ref:
                    content = content.replace(ref, link_path)
                else:
                    attachment_list.append(attachment_link)


        if note_data.get('tag', '') or attachment_list or insert_title \
                or insert_ctime or insert_mtime:
            content = '\n' + content

        content = unquote(content)  #fix uri malformed issue caused by % in url: [ttt](http://www.my.com/1.php?aid=164231&title=2016%3E%%E)

        content = '{}\n{}'.format(create_text_meta_block(), content)
        if meta_data_in_yaml:
            content = '{}\n{}'.format(create_yaml_meta_block(), content)
        #else:
        #    content = '{}\n{}'.format(create_text_meta_block(), content)


        if creation_date_in_filename and note_ctime:
            note_title = time.strftime('%Y-%m-%d ', time.localtime(note_ctime)) + note_title

        note_title_hash = hashlib.sha256(bytes(note_title, 'utf-8')).hexdigest()
        md_file_name = sanitise_path_string(note_title_hash) or 'Untitled'
        md_file_path = Path(parent_notebook.path / '{}.{}'.format(md_file_name, md_file_ext))

        n = 1
        while md_file_path.is_file():
            md_file_path = Path(parent_notebook.path / ('{}_{}.{}'.format(md_file_name, n, md_file_ext)))
            n += 1

        print(f"note file name: {md_file_path}")
        md_file_path.write_text(content, 'utf-8')

        converted_note_ids.append(note_id)

    for notebook in notebook_id_to_path_index.values():
        try:
            notebook.media_path.rmdir()
        except OSError:
            pass

    not_converted_note_ids = set(note_id_to_title_index.keys()) - set(converted_note_ids)

    if not_converted_note_ids:
        print('Failed to convert notes:',
              '\n'.join(('    {} (ID: {})'.format(note_id_to_title_index[note_id], note_id)
                         for note_id in not_converted_note_ids)),
              sep='\n')

    if len(config_data['notebook']) == 1:
        notebook_log_str = 'notebook'
    else:
        notebook_log_str = 'notebooks'

    print('Converted {} {} and {} out of {} notes.\n'.format(len(config_data['notebook']),
                                                             notebook_log_str,
                                                             len(converted_note_ids),
                                                             len(note_id_to_title_index.keys())))
    try:
        recycle_bin_media_path.rmdir()
    except OSError:
        pass

    try:
        recycle_bin_path.rmdir()
    except OSError:
        pass

pandoc_input_file.close()
pandoc_output_file.close()
os.unlink(pandoc_input_file.name)
os.unlink(pandoc_output_file.name)

input('Press Enter to quit...')
