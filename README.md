# grow-ext-google-cloud-images

(WIP) An extension for hosting images in Google Cloud Storage and serving them via
Google's high-performance dynamic image-serving infrastructure.

## Concept

(WIP)

### Features

- Generates URLs for images stored in Google Cloud Storage to serve them via
  Google's high-performance dynamic image-serving infrastructure.
- Provides a reasonable way to append options to generated URLs. Options
  include image format, size, quality, etc.
- Provides a way to request localized images (by identifiers contained within
  the filename).

## Usage

### Initial setup

1. Create an `extensions.txt` file within your pod.
1. Add to the file: `git+git://github.com/grow/grow-ext-google-cloud-images`
1. Run `grow install`.
1. Add the following section to `podspec.yaml`:

```
extensions:
  jinja2:
  - extensions.google_cloud_images.GoogleCloudImagesExtension
```

### In templates

(WIP)

```
# Default image URL.
{{google_image("/bucket/folder/path.jpg").url()}}

# Localized image URL.
{{google_image("/bucket/folder/path.jpg", locale='de').url()}}

# Image URL with 1440 size option appended.
{{google_image("/bucket/folder/path.jpg").url(size=1440)}}
```

### In YAML

(WIP)

```
# Generates a `google_image` object YAML.
image: /bucket/folder/path.jpg !google_image 

# With the following usage in a template.
{{doc.image.url()}}
```

### Builds

(WIP)

## Backend

(WIP)
