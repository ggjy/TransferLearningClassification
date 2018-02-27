import tensorflow as tf
MEAN = [99.73959828, 115.17340629, 121.49871251]


def num_per_epoche(mode):
    if mode == 'train':
        return 12000
    else:
        return 8580


def build_input(database_server, batch_size, mode,
                examples_per_class=None, dataset='dogs120', blur=True, color_switch=False):

    data_path = '???/train_data_batch_*.bin'

    if mode == 'eval' or mode == 'test' or mode == 'val':
        data_path = '???/test_data_batch_*.bin'

    with tf.device('/cpu:0'):
        image_size = 256
        crop_size = 224  # size of input images
        if dataset == 'dogs120':
            label_bytes = 1
            label_offset = 0
            num_classes = 120
        else:
            raise ValueError('Not supported dataset %s', dataset)

        depth = 3
        image_bytes = image_size * image_size * depth
        record_bytes = label_bytes + label_offset + image_bytes

        data_files = tf.gfile.Glob(data_path)
        print 'data files: ', data_files
        file_queue = tf.train.string_input_producer(data_files, shuffle=(mode == 'train'))
        # Read examples from files in the filename queue.
        reader = tf.FixedLengthRecordReader(record_bytes=record_bytes)
        _, value = reader.read(file_queue)

        # Convert these examples to dense labels and processed images.
        record = tf.reshape(tf.decode_raw(value, tf.uint8), [record_bytes])
        label = tf.cast(tf.slice(record, [label_offset], [label_bytes]), tf.int32)
        depth_major = tf.reshape(tf.slice(record, [label_bytes], [image_bytes]),
                                 [depth, image_size, image_size])
        # Convert from [depth, height, width] to [height, width, depth].
        image = tf.cast(tf.transpose(depth_major, [1, 2, 0]), tf.float32)

        if blur:
            image = tf.image.random_brightness(image, max_delta=63. / 255.)
            image = tf.image.random_saturation(image, lower=0.5, upper=1.5)
            image = tf.image.random_contrast(image, lower=0.2, upper=1.8)

        image -= MEAN

        if color_switch:
            img_b, img_g, img_r = tf.split(axis=2, num_or_size_splits=3, value=image)
            image = tf.cast(tf.concat([img_r, img_g, img_b], 2), dtype=tf.float32)

        if mode == 'train':
            image = tf.image.random_flip_left_right(image)
            image = tf.random_crop(image, [crop_size, crop_size, 3])

            example_queue = tf.RandomShuffleQueue(
                capacity=16 * batch_size,
                min_after_dequeue=8 * batch_size,
                dtypes=[tf.float32, tf.int32],
                shapes=[[crop_size, crop_size, depth], [1]])
            num_threads = 16
        else:
            # use bigger image for test and validation.
            example_queue = tf.FIFOQueue(
                3 * batch_size,
                dtypes=[tf.float32, tf.int32],
                shapes=[[image_size, image_size, depth], [1]])
            num_threads = 1

        example_enqueue_op = example_queue.enqueue([image, label])
        tf.train.add_queue_runner(tf.train.queue_runner.QueueRunner(
            example_queue, [example_enqueue_op] * num_threads))

        # Read 'batch' labels + images from the example queue.
        batch_images, batch_labels = example_queue.dequeue_many(batch_size)
        batch_labels = tf.reshape(batch_labels, [batch_size])

        assert len(batch_images.get_shape()) == 4
        assert batch_images.get_shape()[0] == batch_size
        assert batch_images.get_shape()[-1] == 3

        return batch_images, batch_labels