#!/usr/bin/env python

from scipy.io import wavfile
import argparse
import numpy as np
import pygame
import sys
import warnings
import RPi.GPIO as GPIO
import time

TRIG = 23
ECHO = 24

def round_to_nearest(n, m):
    r = n % m
    return n + m - r if r + r >= m else n - r

def speedx(snd_array, factor):
    """ Speeds up / slows down a sound, by some factor. """
    indices = np.round(np.arange(0, len(snd_array), factor))
    indices = indices[indices < len(snd_array)].astype(int)
    return snd_array[indices]


def stretch(snd_array, factor, window_size, h):
    """ Stretches/shortens a sound, by some factor. """
    phase = np.zeros(window_size)
    hanning_window = np.hanning(window_size)
    result = np.zeros(len(snd_array) / factor + window_size)

    for i in np.arange(0, len(snd_array) - (window_size + h), h*factor):
        # Two potentially overlapping subarrays
        a1 = snd_array[i: i + window_size]
        a2 = snd_array[i + h: i + window_size + h]

        # The spectra of these arrays
        s1 = np.fft.fft(hanning_window * a1)
        s2 = np.fft.fft(hanning_window * a2)

        # Rephase all frequencies
        phase = (phase + np.angle(s2/s1)) % 2*np.pi

        a2_rephased = np.fft.ifft(np.abs(s2)*np.exp(1j*phase))
        i2 = int(i/factor)
        result[i2: i2 + window_size] += hanning_window*a2_rephased.real

    # normalize (16bit)
    result = ((2**(16-4)) * result/result.max())

    return result.astype('int16')


def pitchshift(snd_array, n, window_size=2**13, h=2**11):
    """ Changes the pitch of a sound by ``n`` semitones. """
    factor = 2**(1.0 * n / 12.0)
    stretched = stretch(snd_array, 1.0/factor, window_size, h)
    return speedx(stretched[window_size:], factor)


def parse_arguments():
    description = ('Use your computer keyboard as a "piano"')

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        '--wav', '-w',
        metavar='FILE',
        type=argparse.FileType('r'),
        default='bowl.wav',
        help='WAV file (default: bowl.wav)')
    parser.add_argument(
        '--keyboard', '-k',
        metavar='FILE',
        type=argparse.FileType('r'),
        default='typewriter.kb',
        help='keyboard file (default: typewriter.kb)')
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='verbose mode')

    return (parser.parse_args(), parser)

def get_sensor_distance():
        """
        The HC-SR04 sensor requires a short 10uS pulse to trigger the module,
        which will cause the sensor to start the ranging program (8 ultrasound
        bursts at 40 kHz) in order to obtain an echo response. So, to create
        our trigger pulse, we set out trigger pin high for 10uS then set it
        low again.
        """

        GPIO.output(TRIG, True)
        time.sleep(0.00001)
        GPIO.output(TRIG, False)

        """
        Our first step must therefore be to record the last low timestamp for
        ECHO (pulse_start) e.g. just before the return signal is received and
        the pin goes high.
        """

        while GPIO.input(ECHO)==0:
          continue
        pulse_start = time.time()

        """
        Once a signal is received, the value changes from low (0) to high (1),
        and the signal will remain high for the duration of the echo pulse. We
        therefore also need the last high timestamp for ECHO (pulse_end).
        """

        while GPIO.input(ECHO)==1:
          continue
        pulse_end = time.time()      

        """
        We can now calculate the difference between the two recorded timestamps,
        and hence the duration of pulse (pulse_duration), which leads to the
        distance in cm.
        """

        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150
        distance = round(distance, 0)
        time.sleep(0.01)

        return distance

def main():
    GPIO.setmode(GPIO.BCM)

    GPIO.setup(TRIG,GPIO.OUT)
    GPIO.setup(ECHO,GPIO.IN)

    try:
        # Reset the trigger pin to "low"
        GPIO.output(TRIG, False)

        print "Sensor initialised..."
        distance = 0

        # Parse command line arguments
        (args, parser) = parse_arguments()

        # Enable warnings from scipy if requested
        if not args.verbose:
            warnings.simplefilter('ignore')

        fps, sound = wavfile.read(args.wav.name)

        tones = range(-30, 20)
        print('Transponding sound file... ')
        transposed_sounds = [pitchshift(sound, n) for n in tones]
        print('DONE')

        # So flexible ;)
        pygame.mixer.init(fps, -16, 1, 2048)

        distances = range(5, 255, 5)
        sounds = map(pygame.sndarray.make_sound, transposed_sounds)
        distance_sound = dict(zip(distances, sounds))
        is_playing = {d: False for d in distances}

        while True:
            # remember where we were, then detect where we are
            previous_distance = distance
            distance = round_to_nearest(get_sensor_distance(), 5)

            # stop the previous sound, if different
            if previous_distance != distance and previous_distance in is_playing and is_playing[previous_distance]:
                distance_sound[previous_distance].fadeout(50)
                is_playing[previous_distance] = False

            # start the new sound, if valid
            elif distance in is_playing and not is_playing[distance]:
                distance_sound[distance].play(-1,fade_ms=50)
                is_playing[distance] = True
                
    finally:
        GPIO.cleanup()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Goodbye')
