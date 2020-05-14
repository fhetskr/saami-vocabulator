import re
import sys
import urllib.request
import urllib.parse
from html.parser import HTMLParser
from difflib import SequenceMatcher
# wiktionaryparser is needed for translations, but since it's an
# external package I'm leaving this line commented for now
# from wiktionaryparser import WiktionaryParser

def similar(a, b):
	''' get the similarity percentage for two strings '''
	# check if either value passed in is None
	if not (None in (a, b)):
		return SequenceMatcher(None, a, b).ratio()
	else:
		# return 0% match on failure
		return 0

def remove_repeats(input_list):
	''' remove repeat items from a list '''
	# normally it would be cleaner to convert to a set and then back to a list,
	# but here we want to preserve the original order
	new_list = []
	for item in input_list:
		if item not in new_list:
			new_list.append(item)
	return new_list

# this is nothing more than a simple data structure
class DictEntry():
	''' a Saami word and some information about it '''
	word = ""
	pos = ""
	def __init__(self):
		self.translations = {}
		pass
	# two entries are considered equal if they represent the same word
	def __eq__(self, obj):
		try:
			return self.word == obj.word
		except:
			return False
	def __str__(self):
		# this part isn't really necessary, but it was helpful while I was testing
		output = '"{}" ({})\n'.format(self.word, self.pos)
		for translation in self.translations:
			if self.translations.get(translation):
				output += '{}: {}\n'.format(translation, self.translations[translation])
		return output

# it turned out to be a lot easier to translate the parts of speech manually
swedish_parts_of_speech = {
	'subst':'Noun',
	'verb':'Verb',
	'konj':'Conjunction',
	'adj':'Adjective',
	'adj:attr':'Adjective', # Some adjectives are marked as attr or pred, but
	'adj:pred':'Adjective', # since not all of them are I decided to normalize them
	'adj:attr/pred':'Adjective',
	'adv':'Adverb',
	'num':'Numeral'
}

norwegian_parts_of_speech = {
	'subst.':'Noun',
	'egennavn':'Proper noun',
	'verb':'Verb',
	'påpek. pron.':'Pronoun', # I couldn't find a translation for "påpek" anywhere
	'pron.':'Pronoun',
	'adj.':'Adjective',
	'num.':'Numeral'
}

# unfortunately this is not very clean looking, but it's the best the
# python standard libraries had to offer for parsing html
class PiteWordlistReader(HTMLParser):
	
	def __init__(self):
		# initialize the super class
		HTMLParser.__init__(self)
		# this is to keep track of whether the parser should be recording any data
		self.reading_entry = False
		# a list of the entries parsed
		self.entries = []
		self.line_num = 0
		self.last_line = ""

	def handle_starttag(self, tag, attrs):
		# capture data from p tags of menu1 class
		if tag.lower() == 'p' and ('class', 'menu1') in attrs:
			self.reading_entry = True

	def handle_data(self, data):
		# this does nothing if not reading_entry
		if self.reading_entry:
			# do nothing if line is only whitespace
			if (data.strip() == ''):
				return
			# count non-whitespace lines
			self.line_num += 1
			# the second line contains the Saami word
			if (self.line_num == 2):
				self.entries.append(DictEntry())
				self.entries[-1].word = data.strip()
			# line 3 is for part of speech
			elif (self.line_num == 3):
				# all this weird stuff with strip() and split() is necessary because the raw data is messy
				if data.strip().strip('()')[:3] == "ege":
					self.entries[-1].pos = "Proper noun"
				else:
					# we need to translate the parts of speech from Swedish
					self.entries[-1].pos = swedish_parts_of_speech.get(
						data.strip().strip('()').split(')')[0], 'Other')
			# here we check if the last line was the name of a germanic language, and if so then
			# this line should contain that translation
			if (self.last_line == "Engl."):
				self.entries[-1].translations['eng'] = data.split('(')[0].strip()
			if (self.last_line == "Swed."):
				self.entries[-1].translations['swe'] = data.split('(')[0].strip()
			elif (self.last_line == "Norw."):
				self.entries[-1].translations['nor'] = data.split('[')[0].split('(')[0].strip()
			self.last_line = data.strip()

	def handle_endtag(self, tag):
		if tag.lower() == 'p':
			self.line_num = 0
			self.reading_entry = False
			
	def feed(self, data):
		HTMLParser.feed(self, data)
		# the last entry is always blank for some reason, so we just get rid of it
		self.entries.pop()
		return self.entries

class LuleDictReader(HTMLParser):
	
	lule_alphabet = 'aábcdefghijklmnoprstuvwæå'
	lule_dict_url = 'http://gtweb.uit.no/webdict/ak/smj2nob/{}_smj2nob.html'
	reading_entry = False
	entries = []
	td_num = 0
	spans_seen = 0

	def __init__(self):
		HTMLParser.__init__(self)

	def handle_starttag(self, tag, attrs):
		if (tag == 'tr' and not set([('class','normalRow'),('class','alternateRow')]).isdisjoint(attrs)):
			self.reading_entry = True
			self.entries.append(DictEntry())
		if tag == 'td' and self.reading_entry:
			self.td_num += 1
		if self.td_num and tag == 'span':
			self.spans_seen += 1

	def handle_data(self, data):
		if self.reading_entry:
			if self.td_num == 1 and self.spans_seen == 1:
				self.entries[-1].word = data.split(' ')[0].strip()
			if self.td_num == 2 and self.spans_seen == 1:
				if data == '1':
					self.spans_seen -= 1
				else:
					self.entries[-1].translations['nor'] = data.split(',')[0].split(';')[0].split('(')[0].strip()

	def handle_endtag(self, tag):
		if tag == 'tr':
			self.reading_entry = False
			self.td_num = 0
			if self.entries and not self.entries[-1].word:
				self.entries.pop()
		if tag == 'td':
			self.spans_seen = 0

	def feed(self, data):
		HTMLParser.feed(self, data)
		
	def read(self):
		for letter in self.lule_alphabet:
			print(letter)
			page_html = urllib.request.urlopen(self.lule_dict_url.format(urllib.parse.quote(letter))).read()
			self.feed(page_html.decode())
		return self.entries

def getNorthSaamiWords(filename):
	''' retrieves a list of north saami words from a dict file '''
	sme_dict_xml = ''
	# we have to open this in binary mode and decode it because it's unicode
	with open(filename,'rb') as f:
		sme_dict_xml = f.read().decode()
	# the following line is a hackish monstrosity, but it gets the job done
	found_words = re.findall(r'<i>(.*)</i>.*→ </small><kref>(\S*)</kref>.*\n.*<span>(\S.*)</span>', sme_dict_xml)
	found_words = remove_repeats(found_words)
	return found_words

def writeWordlistFile(word_list, filename):
	with open(filename, 'wb') as f:
		for entry in word_list:
			f.write('{};{};{};{};{}\n'.format(entry.word, entry.pos, entry.translations.get('swe', ''), 
				entry.translations.get('nor', ''), entry.translations.get('eng', '')).encode())
def readWordlistFile(filename):
	word_list = []
	lines = []
	with open(filename, 'rb') as f:
		lines = f.readlines()
	for line in lines:
		if line:
			line = line[:-1]
			new_entry = DictEntry()
			contents = line.decode().split(';', 4)
			new_entry.word = contents[0]
			new_entry.pos = contents[1]
			if contents[2]:
				new_entry.translations['swe'] = contents[2]
			if contents[3]:
				new_entry.translations['nor'] = contents[3]
			if contents[4]:
				new_entry.translations['eng'] = contents[4]
			word_list.append(new_entry)
	return word_list
		

def findNorwegianTranslations(word_list):
	''' find English translations for the norwegian words '''
	wp = WiktionaryParser()
	words_checked = 0
	translations_found = 0
	for word in word_list:
		try:
			words_checked += 1
			print('Checking word {}/{} ({} found)'.format(words_checked, len(nsm_words), translations_found), end='\r')
			# Wiktionary forces us to specify if we want Nynorsk or Bokmål
			# so we'll be going with Nynorsk as the default
			json_result = wp.fetch(word.translations['nor'], 'Norwegian Nynorsk')
			# if no translation found for Nynorsk then check Bokmål
			if len(json_result) == 0:
				json_result = wp.fetch(word.translations['nor'], 'Norwegian Bokmål')
			if (len(json_result) > 0):
				entry = json_result[0]
				if entry.get('definitions'):
					# we're just using the first definition listed, and stripping out anything extra
					word.translations['eng'] = re.sub("[\(\[].*?[\)\]]", "",
						entry['definitions'][0]['text'][1]).split(',')[0].strip()
					# we'll get rid of indefinite articles too
					if word.translations['eng'].startswith('a '):
						word.translations['eng'] = word.translations['eng'][2:]
					elif word.translations['eng'].startswith('an '):
						word.translations['eng'] = word.translations['eng'][3:]
					translations_found += 1
		except:
			# if something doesn't work then just ignore it
			pass


lsm_words = readWordlistFile('lule_saami_wordlist.txt')

# get the pite saami data
page_html = ''
# in the final version the script will download assets if needed
with open('pite_wordlist.html', 'rb') as f:
	page_html = f.read().decode()
reader = PiteWordlistReader()
psm_words = reader.feed(page_html)
writeWordlistFile(psm_words, 'pite_saami_wordlist.txt')

# get the north saami data
nsm_words = readWordlistFile('north_saami_wordlist.txt')

print("There are {} words in the Pite Saami dictionary, and {} in the North Saami one\n".format(len(psm_words), len(nsm_words)))

pite_matches_so_far = []
north_matches_so_far = []
# I picked this list totally arbitrarily, but it has given decent results
threshholds = [1.0, 0.95, 0.9, 0.8, 0.7, 0.6, 0.5]
# if a command line argument has been supplied then use that as the name
# of the output file, otherwise call it output.txt
try:
	f = open(sys.argv[1], 'w', encoding='utf-8')
except:
	f = open('output.txt', 'w', encoding='utf-8')

for similarity_threshold in threshholds:
	# each of these needs to be reset at the beginning of each go through the loop
	psm_pos_counter = {}
	nsm_pos_counter = {}
	psm_words_matched = []
	nsm_words_matched = []
	pite_new_counter = 0
	north_new_counter = 0
	f.write(('-' * 80) + '\n')
	
	print("--Checking for matches at {}% threshold--".format(100*similarity_threshold), end='\r')
	f.write('New Pite Saami words matched:\n\n')
	for entry in psm_words:
		# check if the Pite Saami words match at the current similarity threshold
		if similar(entry.word, entry.translations.get('swe')) >= similarity_threshold and entry.pos != 'Proper noun':
			psm_words_matched.append(entry.word)
			if (not entry in pite_matches_so_far):
				pite_matches_so_far.append(entry)
				pite_new_counter += 1
				f.write('{}/{} ({}) - {}\n'.format(entry.word, entry.translations.get('swe', '???'),
					entry.pos, entry.translations.get('eng', '???')))
			if entry.pos not in psm_pos_counter:
				psm_pos_counter[entry.pos] = 1
			else:
				psm_pos_counter[entry.pos] += 1
	f.write("\n{} words matched ({:.2f}%, {} new) for Pite Saami at {}% threshold\nParts of speech:\n\n".format(
		len(psm_words_matched), (len(psm_words_matched) / len(psm_words)) * 100, pite_new_counter, similarity_threshold * 100))
	for pos in psm_pos_counter:
		f.write("{}: {} ({:.2f}%)\n".format(pos, psm_pos_counter[pos], (psm_pos_counter[pos]/len(psm_words_matched)) * 100))
	f.write('\n')

	f.write('\nNew North Saami words matched:\n\n')
	for entry in nsm_words:
		# now check the North Saami words
		if similar(entry.word, entry.translations.get('nor')) >= similarity_threshold and entry.pos != 'Proper noun':
			nsm_words_matched.append(entry)
			if (not entry in north_matches_so_far):
				north_matches_so_far.append(entry)
				north_new_counter += 1
				f.write('{}/{} ({}) - {}\n'.format(entry.word, entry.translations.get('nor', '???'),
					entry.pos, entry.translations.get('eng', '???')))
			if entry.pos not in nsm_pos_counter:
				nsm_pos_counter[entry.pos] = 1
			else:
				nsm_pos_counter[entry.pos] += 1
	f.write("\n{} words matched ({:.2f}%, {} new) for North Saami at {}% threshold\nParts of speech:\n\n".format(
		len(nsm_words_matched), (len(nsm_words_matched) / len(nsm_words)) * 100, north_new_counter, similarity_threshold * 100))
	for pos in nsm_pos_counter:
		f.write("{}: {} ({:.2f}%)\n".format(pos, nsm_pos_counter[pos],
			(nsm_pos_counter[pos]/len(nsm_words_matched)) * 100))
	f.write('\n')

f.close()