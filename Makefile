SHELL := /bin/bash
PATH := $(PATH):$(HOME)/bin

test:
	grow install example
	grow build example
