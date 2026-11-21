import os
import shutil
import subprocess
import tempfile
import uuid

from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError

from mimoza.models import Product, Story


class Command(BaseCommand):
    help = 'Transcode a product or Story video into HLS in the configured media storage.'

    def add_arguments(self, parser):
        parser.add_argument('content_type', choices=('product', 'story'))
        parser.add_argument('object_id', type=int)

    def handle(self, *args, **options):
        content_type = options['content_type']
        model = Product if content_type == 'product' else Story
        video_content = model.objects.filter(pk=options['object_id']).first()
        if video_content is None:
            raise CommandError(f'{content_type.capitalize()} with id {options["object_id"]} was not found.')
        if not video_content.video:
            raise CommandError(f'{content_type.capitalize()} {video_content.pk} has no uploaded video to transcode.')

        ffmpeg_binary = os.environ.get('FFMPEG_BINARY', 'ffmpeg')
        media_collection = 'products' if content_type == 'product' else 'stories'
        output_prefix = f'{media_collection}/hls/{video_content.pk}/{uuid.uuid4().hex}'
        with tempfile.TemporaryDirectory(prefix='mimoza-hls-') as temporary_directory:
            input_path = os.path.join(temporary_directory, 'input-video')
            output_directory = os.path.join(temporary_directory, 'hls')
            os.makedirs(output_directory)
            playlist_path = os.path.join(output_directory, 'index.m3u8')
            segment_pattern = os.path.join(output_directory, 'segment%05d.ts')
            with default_storage.open(video_content.video.name, 'rb') as source:
                with open(input_path, 'wb') as destination:
                    shutil.copyfileobj(source, destination)

            command = [
                ffmpeg_binary,
                '-y',
                '-i', input_path,
                '-c:v', 'libx264',
                '-preset', 'veryfast',
                '-crf', '23',
                '-c:a', 'aac',
                '-b:a', '128k',
                '-hls_time', '6',
                '-hls_playlist_type', 'vod',
                '-hls_flags', 'independent_segments',
                '-hls_segment_filename', segment_pattern,
                playlist_path,
            ]
            try:
                subprocess.run(command, check=True, capture_output=True, text=True)
            except FileNotFoundError as error:
                raise CommandError(
                    f'FFmpeg topilmadi ({ffmpeg_binary}). Uni o‘rnating yoki FFMPEG_BINARY ni sozlang.'
                ) from error
            except subprocess.CalledProcessError as error:
                details = (error.stderr or '').strip()
                raise CommandError(f'FFmpeg HLS yaratolmadi: {details}') from error

            output_files = [
                entry for entry in os.scandir(output_directory)
                if entry.is_file()
            ]
            if (
                not any(entry.name == 'index.m3u8' for entry in output_files)
                or not any(entry.name.endswith('.ts') for entry in output_files)
            ):
                raise CommandError('FFmpeg to‘liq HLS pleylisti va segmentlarini yaratmadi.')

            playlist_key = None
            for output_file in sorted(output_files, key=lambda entry: entry.name):
                storage_key = f'{output_prefix}/{output_file.name}'
                with open(output_file.path, 'rb') as file_handle:
                    saved_key = default_storage.save(storage_key, File(file_handle))
                if output_file.name == 'index.m3u8':
                    playlist_key = saved_key

            if playlist_key is None:
                raise CommandError('FFmpeg pleylist yaratmadi; HLS fayllari saqlanmadi.')

        video_content.hls_playlist.name = playlist_key
        video_content.save(update_fields=['hls_playlist'])
        self.stdout.write(self.style.SUCCESS(
            f'HLS saqlandi: {video_content.hls_playlist.url}'
        ))
