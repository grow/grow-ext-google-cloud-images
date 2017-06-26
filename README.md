# grow-ext-google-cloud-images

[![Build Status](https://travis-ci.org/grow/grow-ext-google-cloud-images.svg?branch=master)](https://travis-ci.org/grow/grow-ext-google-cloud-images)

(WIP) An extension for hosting images in Google Cloud Storage and serving them via
Google's high-performance dynamic image-serving infrastructure.

## Concept

Google offers an API for serving images uploaded to Google Cloud Storage through a high-performance, dynamic image-serving infrastructure. The system provides users with a way to perform a number of operations on images on-the-fly – making it extremely well-suited for developers to implement assets sized, cropped, formatted, etc. in the right way for the user – with no added work.

For example, the image-serving infrastructure can reformat (JPG, PNG, WEBP), resize or crop, and transform the image in a number of ways on-the-fly.

Here's the workflow:

1. Upload an image to Google Cloud Storage.
1. Ensure the backend microservice has read access to the object in GCS. (More on this below).
1. Use the template function or YAML extension provided in this extension.
1. Supply options to the extension to generate the right URL.

Here are a few live examples:

```
# Resize to 100 pixels wide
s100
```
![](https://lh3.googleusercontent.com/UN7taQ_uv67DQ2BO_WAc5i-b_KHPl4hWXQYG9dj_8FesTSruE_k-AyPId2Jc1DujAMP_kFpD413i8T4TK-O_=s100)

```
# Smart crop, border 100%, format PNG, size 200
pp-br100-rp-s200
```
![](https://lh3.googleusercontent.com/UN7taQ_uv67DQ2BO_WAc5i-b_KHPl4hWXQYG9dj_8FesTSruE_k-AyPId2Jc1DujAMP_kFpD413i8T4TK-O_=pp-br100-rp-s200)

```
# Size 200, rotate 90
s200-r90
```
![](https://lh3.googleusercontent.com/UN7taQ_uv67DQ2BO_WAc5i-b_KHPl4hWXQYG9dj_8FesTSruE_k-AyPId2Jc1DujAMP_kFpD413i8T4TK-O_=s200-r90)

```
# Width 100, height 300, crop, smart crop, quality 100, format JPG
w100-h300-c-pp-l100-rj
```
![](https://lh3.googleusercontent.com/UN7taQ_uv67DQ2BO_WAc5i-b_KHPl4hWXQYG9dj_8FesTSruE_k-AyPId2Jc1DujAMP_kFpD413i8T4TK-O_=w100-h300-c-pp-l100-rj)


### Features

- Generates URLs for images stored in Google Cloud Storage to serve them via
  Google's high-performance dynamic image-serving infrastructure.
- Provides a reasonable way to append options to generated URLs. Options
  include image format, size, quality, etc.
- Provides a way to request localized images (by identifiers contained within
  the filename).

## Usage

### Grow setup

1. Create an `extensions.txt` file within your pod.
1. Add to the file: `git+git://github.com/grow/grow-ext-google-cloud-images`
1. Run `grow install`.
1. Add the following section to `podspec.yaml`:

```
extensions:
  jinja2:
  - extensions.google_cloud_images.GoogleCloudImagesExtension
  preprocessors:
  - extensions.google_cloud_images.GoogleCloudImagesPreprocessor

preprocessors:
- kind: google_cloud_images
  backend: https://gci.grow.io  # URL to backend service.
```

### Google Cloud Storage setup

Note that this extension requires you to grant __OWNER__ access on your GCS
objects to a service account corresponding to the microservice responsible for
generating URLs. The account you grant access to depends upon the microservice.

1. Visit the backend to learn which service account to grant access to. A
   sample backend runs at https://gci.grow.io. A service account might look
   like the following: `grow-prod@appspot.gserviceaccount.com`.

1. Create or reuse an existing Google Cloud Storage bucket. Note that since
   __OWNER__ access is required by the URL generation API, we recommend using a
   bucket specifically for uploading assets to this service.

```shell
# Create a new bucket.
gsutil mb -p <project> gs://<bucket>

# Set the default ACL for objects uploaded to the bucket. Note the below
# command grants OWNER access to the service account.
gsutil defacl ch -u account@example.com:O gs://<bucket>

# Upload assets to the Google Cloud Storage bucket.
gsutil cp file.jpg gs://<bucket>/<path>/
```

### Usage in templates

(WIP)

```
# Default image URL.
{{google_image("/bucket/folder/path.jpg").url()}}

# Image URL with 1440 size option appended.
{{google_image("/bucket/folder/path.jpg").url(['s1440'])}}

# Localized image URL.
{{google_image("/bucket/folder/path.jpg", locale='de').url()}}
```

## URL options

The `url` method of `GoogleCloudImage` objects accepts a list of options to
append to the URLs generated by Google's image-serving infrastructure. The
options determine the behavior of the image served.

The following optios can be provided to the `url` method. [See details on
StackOverflow](https://stackoverflow.com/q/25148567).

### Size and crop

- s640 — generates image 640 pixels on largest dimension
- s0 — original size image
- w100 — generates image 100 pixels wide
- h100 — generates image 100 pixels tall
- s (without a value) — stretches image to fit dimensions
- c — crops image to provided dimensions
- n — same as c, but crops from the center
- p — smart square crop, attempts cropping to faces
- pp — alternate smart square crop, does not cut off faces (?)
- cc — generates a circularly cropped image
- ci — square crop to smallest of: width, height, or specified =s parameter
- nu — no-upscaling. Disables resizing an image to larger than its original
  resolution.

### Rotation

- fv — flip vertically
- fh — flip horizontally
- r{90, 180, 270} — rotates image 90, 180, or 270 degrees clockwise

### Format

- rj — forces the resulting image to be JPG
- rp — forces the resulting image to be PNG
- rw — forces the resulting image to be WebP
- rg — forces the resulting image to be GIF
- v{0,1,2,3} — sets image to a different format option (works with JPG and WebP)
- j{number} — set quality

### Animated GIF

- rh — generates an MP4 from the input image
- k — kill animation (generates static image)

### Miscellaneous

- b10 — add a 10px border to image
- c0xAARRGGBB — set border color, eg. =c0xffff0000 for red
- d — adds header to cause browser download
- e7 — set cache-control max-age header on response to 7 days
- l100 — sets JPEG quality to 100% (1-100)
- h — responds with an HTML page containing the image
- g — responds with XML used by Google's pan/zoom
