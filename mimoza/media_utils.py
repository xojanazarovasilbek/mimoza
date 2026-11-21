import os
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps


def convert_image_field_to_webp(instance, field_name):
    image_field = getattr(instance, field_name)
    if not image_field:
        return
    filename = os.path.splitext(os.path.basename(image_field.name.replace('\\', '/')))[0] + '.webp'
    if image_field._committed and image_field.name.lower().endswith('.webp'):
        return

    image_field.open('rb')
    with Image.open(image_field) as source:
        if source.format == 'WEBP':
            if image_field.name.lower().endswith('.webp'):
                return
            image_field.seek(0)
            image_field.save(filename, ContentFile(image_field.read()), save=False)
            return
        frames = []
        durations = []
        frame_index = 0
        while True:
            source.seek(frame_index)
            frame = ImageOps.exif_transpose(source.copy())
            if frame.mode not in ('RGB', 'RGBA'):
                frame = frame.convert('RGBA' if 'transparency' in frame.info else 'RGB')
            frames.append(frame)
            durations.append(source.info.get('duration', 100))
            frame_index += 1
            try:
                source.seek(frame_index)
            except EOFError:
                break

        output = BytesIO()
        frames[0].save(
            output,
            format='WEBP',
            save_all=len(frames) > 1,
            append_images=frames[1:],
            duration=durations,
            loop=source.info.get('loop', 0),
            quality=85,
            method=6,
        )

    image_field.save(filename, ContentFile(output.getvalue()), save=False)


class WebPImageModel:
    webp_image_fields = ()

    def save(self, *args, **kwargs):
        old_names = {}
        if self.pk and self.webp_image_fields:
            old_names = (
                type(self).objects.filter(pk=self.pk)
                .values(*self.webp_image_fields)
                .first()
                or {}
            )
        converted_fields = []
        for field_name in self.webp_image_fields:
            convert_image_field_to_webp(self, field_name)
            image_field = getattr(self, field_name)
            new_name = image_field.name if image_field else ''
            if self.pk and (old_names.get(field_name) or '') != (new_name or ''):
                converted_fields.append(field_name)

        update_fields = kwargs.get('update_fields')
        if update_fields is not None and converted_fields:
            kwargs['update_fields'] = set(update_fields).union(converted_fields)

        super().save(*args, **kwargs)

        for field_name, old_name in old_names.items():
            new_name = getattr(self, field_name).name
            if old_name and old_name != new_name and not type(self).objects.filter(
                **{field_name: old_name}
            ).exclude(pk=self.pk).exists():
                self._meta.get_field(field_name).storage.delete(old_name)
