// PB-42: Bangla / English switch.
// The pages are written in English. In Bangla mode, every phrase on screen that is in the dictionary below is
// replaced after the page is drawn (a MutationObserver watches for new content). Text that people typed (titles,
// descriptions, messages) is never in the dictionary, so it is shown as written.

import { html } from './ui.js';

const STORE_KEY = 'pfb-language';

const BN = {
  // menu and header
  'Find homes': 'বাড়ি খুঁজুন', 'Price guide': 'দামের গাইড', 'Calculators': 'ক্যালকুলেটর', 'Saved': 'সংরক্ষিত',
  'Visits': 'বাড়ি দেখা', 'Inquiries': 'জিজ্ঞাসা', 'Consultations': 'পরামর্শ', 'Agreements': 'চুক্তি', 'History': 'ইতিহাস',
  'My listings': 'আমার বিজ্ঞাপন', 'Verification queue': 'যাচাইয়ের তালিকা', 'Browse listings': 'বিজ্ঞাপন দেখুন',
  'Admin panel': 'অ্যাডমিন প্যানেল', 'My application': 'আমার আবেদন', 'Log in': 'লগ ইন', 'Sign up': 'সাইন আপ',
  'Log out': 'লগ আউট', 'Menu': 'মেনু', 'Notifications': 'নোটিফিকেশন', 'Buyer / Tenant': 'ক্রেতা / ভাড়াটিয়া',
  'Owner': 'মালিক', 'Advocate': 'আইনজীবী', 'Admin': 'অ্যাডমিন', 'Skip to content': 'মূল অংশে যান',
  'Loading…': 'লোড হচ্ছে…', 'You are logged out.': 'আপনি লগ আউট করেছেন।',
  'My profile': 'আমার প্রোফাইল', 'Location': 'অবস্থান', 'Get directions': 'দিকনির্দেশনা দেখুন',
  'Open in Google Maps': 'গুগল ম্যাপে খুলুন', 'Open': 'খুলুন', 'You are here': 'আপনি এখানে', 'Try again': 'আবার চেষ্টা করুন',
  'We could not get your location': 'আপনার অবস্থান পাওয়া যায়নি', 'Finding you…': 'আপনাকে খোঁজা হচ্ছে…',
  // search page
  'Find a home you can trust': 'বিশ্বাস করা যায় এমন বাড়ি খুঁজুন',
  'Buy or rent across Bangladesh, with legal papers checked by an advocate.':
    'সারা বাংলাদেশে বাড়ি কিনুন বা ভাড়া নিন, আইনজীবীর যাচাই করা কাগজপত্রসহ।',
  'All': 'সব', 'Buy': 'কিনুন', 'Rent': 'ভাড়া', 'Sale': 'বিক্রি', 'Area or city': 'এলাকা বা শহর', 'Search': 'খুঁজুন',
  'Area or city, e.g. Gulshan, Dhanmondi, Sylhet': 'এলাকা বা শহর, যেমন গুলশান, ধানমন্ডি, সিলেট',
  'Property type': 'বাড়ির ধরন', 'Any type': 'যেকোনো ধরন', 'District': 'জেলা', 'Any district': 'যেকোনো জেলা',
  'All districts': 'সব জেলা', 'Bedrooms': 'শোবার ঘর', 'Any': 'যেকোনো', 'Furnished': 'আসবাবসহ', 'Unfurnished': 'আসবাব ছাড়া',
  'Sort by': 'সাজান', 'Verified first': 'যাচাইকৃত আগে', 'Newest': 'নতুন আগে', 'Price: low to high': 'দাম: কম থেকে বেশি',
  'Price: high to low': 'দাম: বেশি থেকে কম', 'Nearest first': 'কাছের আগে', 'Near a place': 'কোনো জায়গার কাছে',
  'Anywhere': 'যেকোনো জায়গা', 'My location': 'আমার অবস্থান', 'Within': 'দূরত্ব', 'Use my location': 'আমার অবস্থান ব্যবহার করুন',
  'Verified only': 'শুধু যাচাইকৃত', 'Clear': 'মুছুন', 'Min price (৳)': 'সর্বনিম্ন দাম (৳)', 'Max price (৳)': 'সর্বোচ্চ দাম (৳)',
  'Min rent / month (৳)': 'সর্বনিম্ন ভাড়া / মাস (৳)', 'Max rent / month (৳)': 'সর্বোচ্চ ভাড়া / মাস (৳)',
  'Search by district': 'জেলা অনুযায়ী খুঁজুন', 'Pick a district to see the homes listed there.': 'একটি জেলা বেছে নিন, সেখানকার বাড়িগুলো দেখুন।',
  'Sell or rent out your property': 'আপনার বাড়ি বিক্রি বা ভাড়া দিন', 'List your property': 'আপনার বাড়ির বিজ্ঞাপন দিন',
  'Add your property details': 'বাড়ির তথ্য দিন', 'Upload your legal papers': 'আইনি কাগজপত্র আপলোড করুন',
  'Get the Verified badge': 'যাচাইকৃত ব্যাজ পান', 'Why Property Finder Bangladesh': 'কেন প্রপার্টি ফাইন্ডার বাংলাদেশ',
  'Papers checked by an advocate': 'আইনজীবীর যাচাই করা কাগজপত্র', 'See verified homes': 'যাচাইকৃত বাড়ি দেখুন',
  'The full move-in cost, up front': 'ওঠার পুরো খরচ, আগেই জানুন', 'Browse homes for rent': 'ভাড়ার বাড়ি দেখুন',
  'Know what you can afford': 'আপনার সাধ্য জানুন', 'Open the calculators': 'ক্যালকুলেটর খুলুন',
  'List': 'তালিকা', 'Map': 'মানচিত্র', 'Showing verified listings only': 'শুধু যাচাইকৃত বিজ্ঞাপন দেখানো হচ্ছে',
  'No homes match your search yet': 'আপনার খোঁজার সাথে মেলে এমন কোনো বাড়ি এখনো নেই', 'Show all homes': 'সব বাড়ি দেখুন',
  'No homes to show on the map.': 'মানচিত্রে দেখানোর মতো কোনো বাড়ি নেই।', '← Previous': '← আগের', 'Next →': 'পরের →',
  'Save this search': 'এই খোঁজ সংরক্ষণ করুন',
  // listing cards and badges
  'For rent': 'ভাড়া', 'For sale': 'বিক্রি', 'Verified': 'যাচাইকৃত', 'Unverified': 'যাচাই হয়নি',
  'Document Verified': 'কাগজ যাচাইকৃত', 'Site Visited': 'সরেজমিনে দেখা', 'Fully Verified': 'সম্পূর্ণ যাচাইকৃত',
  'Apartment': 'অ্যাপার্টমেন্ট', 'House': 'বাড়ি', 'Duplex': 'ডুপ্লেক্স', 'Studio': 'স্টুডিও', 'Plot': 'প্লট', 'Commercial': 'বাণিজ্যিক',
  'Dhaka': 'ঢাকা', 'Chattogram': 'চট্টগ্রাম', 'Sylhet': 'সিলেট', 'Rajshahi': 'রাজশাহী', 'Khulna': 'খুলনা', 'Barishal': 'বরিশাল',
  'Rangpur': 'রংপুর', 'Mymensingh': 'ময়মনসিংহ', '/ month': '/ মাস',
  // listing page
  '← Back to search': '← খোঁজে ফিরে যান', 'Asking price': 'চাওয়া দাম', 'Estimate the monthly EMI': 'মাসিক কিস্তি হিসাব করুন',
  'Monthly rent': 'মাসিক ভাড়া', "First month's rent": 'প্রথম মাসের ভাড়া', 'Security deposit': 'জামানত',
  'Total move-in cost': 'মোট ওঠার খরচ', 'Move-in cost': 'ওঠার খরচ', 'Available from': 'যেদিন থেকে পাওয়া যাবে',
  'Minimum lease': 'সর্বনিম্ন মেয়াদ', 'Utilities': 'ইউটিলিটি বিল', 'Included': 'অন্তর্ভুক্ত', 'Not included': 'অন্তর্ভুক্ত নয়',
  'Preferred tenant': 'পছন্দের ভাড়াটিয়া', 'Family': 'পরিবার', 'Bachelor': 'ব্যাচেলর', 'Anyone': 'যে কেউ',
  'Can I afford this rent?': 'এই ভাড়া কি আমার সাধ্যের মধ্যে?', 'Type': 'ধরন', 'Bathrooms': 'বাথরুম', 'Size': 'আয়তন',
  'Listed': 'বিজ্ঞাপনের তারিখ', 'Yes': 'হ্যাঁ', 'No': 'না', 'About this home': 'বাড়িটি সম্পর্কে',
  'Download the legal report (PDF)': 'আইনি রিপোর্ট ডাউনলোড করুন (PDF)', 'Ask an Advocate': 'আইনজীবীকে জিজ্ঞাসা করুন',
  'Get legal help about this property before you decide.': 'সিদ্ধান্ত নেওয়ার আগে এই বাড়ি নিয়ে আইনি সাহায্য নিন।',
  'Log in to ask an advocate': 'আইনজীবীকে জিজ্ঞাসা করতে লগ ইন করুন', 'Ask a free question': 'বিনামূল্যে প্রশ্ন করুন',
  'Book a paid consultation': 'পেইড পরামর্শ বুক করুন', 'Contact the owner': 'মালিকের সাথে যোগাযোগ',
  'Your phone number': 'আপনার ফোন নম্বর', 'Send inquiry': 'বার্তা পাঠান', '♡ Save home': '♡ সংরক্ষণ করুন', '♥ Saved': '♥ সংরক্ষিত',
  'Interested?': 'আগ্রহী?', 'Log in to contact the owner': 'মালিকের সাথে যোগাযোগ করতে লগ ইন করুন',
  'Report this listing': 'এই বিজ্ঞাপনটি রিপোর্ট করুন', 'This is your listing': 'এটি আপনার বিজ্ঞাপন', 'Edit listing': 'বিজ্ঞাপন সম্পাদনা',
  'Visit this home': 'বাড়িটি দেখতে যান', 'Day': 'দিন', 'Time': 'সময়', 'Ask for this visit': 'দেখার সময় চান',
  'Log in to book a visit': 'দেখার সময় বুক করতে লগ ইন করুন', 'Cancel visit': 'দেখা বাতিল করুন', 'All my visits': 'আমার সব বাড়ি দেখা',
  '+ Compare': '+ তুলনা', '✓ In compare list': '✓ তুলনার তালিকায়', '✓ Phone verified': '✓ ফোন যাচাইকৃত',
  'Compare homes': 'বাড়ি তুলনা', 'Best': 'সেরা',
  // log in and sign up
  'Welcome back to Property Finder Bangladesh.': 'প্রপার্টি ফাইন্ডার বাংলাদেশে আবার স্বাগতম।', 'Email': 'ইমেইল',
  'Password': 'পাসওয়ার্ড', 'New here?': 'নতুন?', 'Create an account': 'অ্যাকাউন্ট খুলুন', 'Demo accounts': 'ডেমো অ্যাকাউন্ট',
  'Choose how you will use Property Finder Bangladesh.': 'প্রপার্টি ফাইন্ডার বাংলাদেশ কীভাবে ব্যবহার করবেন তা বেছে নিন।',
  'I want to': 'আমি চাই', 'Buy or rent': 'কিনতে বা ভাড়া নিতে',
  'Search homes, save favorites, contact owners.': 'বাড়ি খুঁজুন, পছন্দ সংরক্ষণ করুন, মালিকের সাথে যোগাযোগ করুন।',
  'Sell or rent out': 'বিক্রি বা ভাড়া দিতে', 'List property and get it legally verified.': 'বাড়ির বিজ্ঞাপন দিন এবং আইনি যাচাই করান।',
  'Work as an advocate': 'আইনজীবী হিসেবে কাজ করতে', 'Full name': 'পুরো নাম', 'Mobile number': 'মোবাইল নম্বর',
  'Create account': 'অ্যাকাউন্ট খুলুন', 'Already have an account?': 'আগেই অ্যাকাউন্ট আছে?',
  'Apply as an advocate': 'আইনজীবী হিসেবে আবেদন করুন',
  // footer
  'Explore': 'ঘুরে দেখুন', 'Homes for sale': 'বিক্রির বাড়ি', 'Homes for rent': 'ভাড়ার বাড়ি', 'Verified homes': 'যাচাইকৃত বাড়ি',
  'Owners and advocates': 'মালিক ও আইনজীবী',
};

// Phrases with a number or a name inside.
const PATTERNS = [
  [/^(\d+) homes? for rent$/, 'ভাড়ার জন্য $1টি বাড়ি'],
  [/^(\d+) homes? for sale$/, 'বিক্রির জন্য $1টি বাড়ি'],
  [/^(\d+) homes?$/, '$1টি বাড়ি'],
  [/^(\d+) bed$/, '$1 শোবার ঘর'],
  [/^(\d+) bath$/, '$1 বাথরুম'],
  [/^(\d+) months$/, '$1 মাস'],
  [/^([\d.]+) km$/, '$1 কিমি'],
  [/^([\d.]+) km away$/, '$1 কিমি দূরে'],
  [/^([\d.]+) km from (.+)$/, '$2 থেকে $1 কিমি'],
  [/^Listed by (.+)$/, 'বিজ্ঞাপন দিয়েছেন: $1'],
  [/^Deposit (.+) · Move-in (.+)$/, 'জামানত $1 · ওঠার খরচ $2'],
  [/^Compare (\d+) homes? →$/, '$1টি বাড়ি তুলনা করুন →'],
  [/^Showing (\d+)–(\d+) · page (\d+) of (\d+)$/, '$1–$2 দেখানো হচ্ছে · পাতা $3 / $4'],
];

// Never translated: typed text, the language button itself and anything marked data-no-translate.
const SKIP = 'script, style, textarea, input, select[data-no-translate], [data-no-translate], .chat-bubble, .notes-box, .card-title, .lang-switch';
const ATTRIBUTES = ['placeholder', 'aria-label', 'title'];

function readLanguage() {
  try {
    return localStorage.getItem(STORE_KEY) === 'bn' ? 'bn' : 'en';
  } catch {
    return 'en';
  }
}

let language = readLanguage();

export function translatePhrase(text) {
  const trimmed = text.trim();
  if (!trimmed) return null;
  if (Object.hasOwn(BN, trimmed)) return text.replace(trimmed, BN[trimmed]);
  for (const [pattern, replacement] of PATTERNS) {
    if (pattern.test(trimmed)) return text.replace(trimmed, trimmed.replace(pattern, replacement));
  }
  return null;
}

function translateElementAttributes(element) {
  for (const name of ATTRIBUTES) {
    const value = element.getAttribute?.(name);
    if (value) {
      const done = translatePhrase(value);
      if (done) element.setAttribute(name, done);
    }
  }
}

export function translate(node) {
  if (language !== 'bn' || !node) return;
  if (node.nodeType === Node.TEXT_NODE) {
    const parent = node.parentElement;
    if (!parent || parent.closest(SKIP)) return;
    const done = translatePhrase(node.data);
    if (done === null) return;
    // An <option> without a value sends its text: keep the English value so forms still work.
    if (parent.tagName === 'OPTION' && !parent.hasAttribute('value')) parent.setAttribute('value', node.data.trim());
    node.data = done;
    return;
  }
  if (node.nodeType !== Node.ELEMENT_NODE || node.closest(SKIP)) return;
  translateElementAttributes(node);
  const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
  let current = walker.nextNode();
  while (current) {
    const next = walker.nextNode();
    if (current.nodeType === Node.ELEMENT_NODE) translateElementAttributes(current);
    else translate(current);
    current = next;
  }
}

export function languageSwitch() {
  const other = language === 'bn' ? 'en' : 'bn';
  return html`<button class="lang-switch" type="button" data-language="${other}" lang="${other}"
    title="${other === 'bn' ? 'বাংলায় দেখুন' : 'Show in English'}">${other === 'bn' ? 'বাংলা' : 'English'}</button>`;
}

// Starts translating new content and handles the switch. Switching back to English reloads the page,
// so the original English text comes back exactly.
export function setUpLanguage() {
  document.documentElement.lang = language;
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-language]');
    if (!button) return;
    try {
      localStorage.setItem(STORE_KEY, button.dataset.language);
    } catch {
      // Storage blocked: the choice lasts for this page only.
    }
    if (button.dataset.language === 'en') {
      location.reload();
      return;
    }
    language = 'bn';
    document.documentElement.lang = 'bn';
    translate(document.body);
    button.dataset.language = 'en';
    button.lang = 'en';
    button.textContent = 'English';
  });
  translate(document.body);
  new MutationObserver(mutations => {
    if (language !== 'bn') return;
    for (const mutation of mutations) {
      for (const added of mutation.addedNodes) translate(added);
    }
  }).observe(document.body, { childList: true, subtree: true });
}
