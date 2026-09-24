"""Word lists used by the rule-based attacker's name and ZIP code detectors.

Everything here is plain data so the detectors stay deterministic and need no
third-party packages. Lists are deliberately modest: they aim at the common
cases a regex attacker can catch with high precision, not at full coverage.
"""

from __future__ import annotations

# Common given names in the US and UK, plus frequent names from large
# minority communities in both countries. Names that are far more often an
# ordinary capitalised word or a place (April, May, June, August, Will, Bill,
# Grant, Hope, Faith, Joy, Amber, Hunter, Chase, Morgan, Chelsea, Sydney,
# Georgia, Virginia, Paris, Dallas and similar) are left out on purpose, so
# "May Day" or "Georgia Tech" never reads as a person.
FIRST_NAMES = frozenset(
    """
    Aaliyah Aaron Abby Abdul Abigail Adam Addison Adrian Adriana Agnes Ahmad Ahmed
    Aidan Aiden Aisha Alan Albert Alejandra Alejandro Alex Alexander Alexandra
    Alexis Alfie Alfred Ali Alice Alicia Alison Alistair Allison Alyssa Amanda
    Amelia Amir Amira Amit Amy Ana Ananya Andrea Andrew Andy Angela Angus Anita
    Ann Anna Anne Annie Anthony Antonio Archie Aria Arjun Arthur Ashley Audrey
    Ava Barbara Barry Beatrice Ben Benjamin Bernard Beth Bethany Betty Beverly
    Bilal Billy Bobby Brandon Brenda Brian Brianna Bridget Brittany Bruce Bryan
    Caitlin Caleb Callum Camila Carl Carla Carlos Carmen Carol Caroline Carolyn
    Catherine Charles Charlie Charlotte Cheryl Chloe Chris Christian Christina
    Christine Christopher Claire Clara Clare Claudia Clive Colin Connor Craig
    Curtis Cynthia Daisy Dan Dana Daniel Daniela Danielle Danny Darren Dave David
    Dean Debbie Deborah Debra Declan Denise Dennis Derek Diana Diane Diego Dolores
    Donald Donna Doris Dorothy Douglas Dylan Eddie Edith Edward Edwin Eileen Elaine
    Eleanor Elena Eli Elijah Elizabeth Ella Ellen Ellie Elliot Elliott Emily Emma
    Eric Erica Erin Esther Ethan Eugene Evan Evelyn Evie Ezra Faisal Fatima Felix
    Fernando Fiona Finn Florence Frances Francesca Francis Francisco Frank Fraser
    Fred Freddie Frederick Freya Gabriel Gabriela Gareth Gary Gavin Gemma George
    Gerald Gillian Gloria Gordon Graham Grace Greg Gregory Guadalupe Hamza Hannah
    Harold Harriet Harry Harvey Hassan Hayley Hazel Heather Helen Henry Holly
    Howard Hugh Hugo Hussein Ian Ibrahim Imogen Imran Irene Isaac Isabel Isabella
    Isla Ivan Jack Jackie Jacob Jacqueline Jake James Jamie Jan Jane Janet Janice
    Jasmine Jason Jasper Javier Jayden Jean Jeff Jeffrey Jennifer Jenny Jeremy
    Jerry Jesse Jessica Jill Jim Jimmy Joan Joanna Joanne Joe Joel John Johnny Jon
    Jonathan Jordan Jorge Jose José Joseph Josephine Joshua Joyce Juan Judith Judy
    Julia Julian Julie Justin Karen Karim Kate Katherine Kathleen Kathryn Kathy
    Katie Kayla Keith Kelly Ken Kenneth Kerry Kevin Khalid Kieran Kimberly Kirsty
    Kyle Kylie Laura Lauren Lawrence Layla Leah Leanne Lee Leila Leo Leon Leonard
    Levi Lewis Liam Lily Linda Lindsay Lisa Logan Lorraine Louis Louise Lucas Lucia
    Lucy Luis Luke Lynn Madeline Madison Maggie Malcolm Mandy Manuel Marcus
    Margaret Maria Marie Marilyn Marion Mark Martha Martin Mary Maryam Mason
    Mateo Matilda Matt Matthew Maureen Max Maya Megan Mei Melanie Melissa Mia
    Michael Michelle Miguel Mike Mildred Millie Miriam Mohamed Mohammad Mohammed
    Molly Monica Moshe Muhammad Mustafa Nadia Naomi Natalie Natasha Nathan
    Nathaniel Neil Nicholas Nick Nicola Nicole Nigel Nina Noah Noor Nora Norma
    Norman Olivia Omar Oliver Oscar Owen Pamela Patricia Patrick Paul Paula
    Pauline Pedro Penelope Peter Philip Phillip Phoebe Poppy Priya Rachael Rachel
    Rafael Rahul Raj Rajesh Ralph Randy Ravi Raymond Rebecca Reece Rhys Ricardo
    Richard Riley Rita Rob Robert Roger Ronald Rory Rosa Rose Rosemary Rosie Ross
    Roy Ruby Rupert Russell Ruth Ryan Sally Samantha Samir Samuel Sana Sandra
    Sanjay Sara Sarah Savannah Scarlett Scott Sean Sebastian Sergio Seth Shane
    Shannon Sharon Shawn Sheila Shirley Sian Simon Siobhan Sofia Sophia Sophie
    Stacey Stanley Stella Stephanie Stephen Steve Steven Stuart Susan Tanya Tariq
    Taylor Teresa Terry Theo Theodore Theresa Thomas Tiffany Tim Timothy Tina Toby
    Tom Tommy Tony Tracey Tracy Travis Trevor Tyler Valentina Valerie Vanessa
    Veronica Vicky Victor Victoria Vikram Vincent Violet Walter Wayne Wei Wendy
    William Willie Yasmin Yusuf Yvonne Zachary Zara Zoe Zoey
    """.split()
)

# Lowercase words that end a run of capitalised name tokens. A run is cut at
# the first of these, so "Dr Smith Monday" gives "Smith" and "Patient Safety"
# gives nothing. Covers months, days, function words, pronouns, honorifics,
# redaction placeholders and common title-case nouns that follow "Patient" or
# "Client" in institutional text.
NAME_STOP_WORDS = frozenset(
    """
    january february march april may june july august september sept october
    november december feb mar apr jun jul aug sep oct nov dec
    monday tuesday wednesday thursday friday saturday sunday
    mon tue tues wed thu thur thurs fri sat sun
    morning afternoon evening night today tomorrow yesterday christmas easter
    a an and or but nor not the this that these those there here then than
    of in on at to for from with by about as into onto over under after before
    is was are were be been has had have will would shall should can could may
    might must do does did said says told asked who whom whose which what when
    where why how
    he she they we you it i me him her them us his hers their theirs our your its
    my mine
    mr mrs ms miss mx dr prof sir dame
    redacted anonymised anonymized anonymous anon withheld removed hidden masked
    deleted omitted confidential private unknown none null blank tbc tbd na
    patient patients client clients person people name surname forename
    safety care records record notes portal transport information experience
    advice liaison access support advocate advocacy relations account feedback
    satisfaction outcomes education leaflet participation choice voice journey
    pathway reference number id identifier details demographics summary history
    consent status list registry register zero discharge admission assessment
    review guide charter rights forum panel success manager onboarding agreement
    contract data file files side area zone code
    new
    england scotland wales ireland britain uk usa america europe africa asia
    canada australia mexico india china pakistan italy france spain germany
    """.split()
)

# Lowercase words that mark a capitalised run as an organisation, place,
# building, street or named condition rather than a person. If one appears in
# the run before it is cut, the whole run is rejected: "Acme Labs",
# "John Radcliffe Hospital", "Jordan Valley", "Addison's Disease". Words that
# are also common surnames (Hall, Hill, Lane, Park, Church, Law, Ward, Court,
# Castle) are left out, so "Jane Hill" still counts as a name at the cost of
# also flagging "Victoria Park". Ward is handled in the detector instead.
NAME_ENTITY_WORDS = frozenset(
    """
    street st road rd avenue ave ln drive boulevard blvd way ct place pl terrace
    close crescent parkway highway hwy square sq circle mews grove station line
    airport bridge river lake bay valley hills heights island islands beach
    forest mountain mountains falls springs creek harbor harbour palace tower
    house building estate village town city county state province district
    borough region wing unit suite garden gardens
    hospital clinic surgery practice centre center chapel cathedral
    mosque temple synagogue museum gallery library theatre theater stadium arena
    hotel inn restaurant cafe café bar pub shop store stores market mall pharmacy
    school college university institute academy
    labs lab laboratory laboratories inc ltd llc llp plc corp corporation company
    co group holdings partners partnership associates solutions systems
    technologies tech bank
    council board committee commission agency authority department ministry
    office service services society association union club fc team
    foundation trust charity fund appeal league show cup bowl award awards prize
    medal memorial project programme program scheme act day
    disease syndrome palsy lymphoma sarcoma scale test score method effect
    theorem principle aid science democrat democrats democratic
    """.split()
)

# Words that, directly before a first name or title, turn it into a place or
# institution name: "St John Ambulance", "Lake Charles", "Fort William",
# "Notre Dame".
NAME_PLACE_PREFIXES = frozenset(
    "st saint san santa fort ft port mount mt lake cape glen notre".split()
)

# Lowercase name particles allowed inside a run when followed by a
# capitalised token: "Ludwig van Beethoven", "Maria de la Cruz".
NAME_PARTICLES = frozenset(
    "van von der den de del della di da dos das du la le bin ibn al el ter ten".split()
)

US_STATE_NAMES = (
    "Alabama",
    "Alaska",
    "Arizona",
    "Arkansas",
    "California",
    "Colorado",
    "Connecticut",
    "Delaware",
    "District of Columbia",
    "Florida",
    "Georgia",
    "Hawaii",
    "Idaho",
    "Illinois",
    "Indiana",
    "Iowa",
    "Kansas",
    "Kentucky",
    "Louisiana",
    "Maine",
    "Maryland",
    "Massachusetts",
    "Michigan",
    "Minnesota",
    "Mississippi",
    "Missouri",
    "Montana",
    "Nebraska",
    "Nevada",
    "New Hampshire",
    "New Jersey",
    "New Mexico",
    "New York",
    "North Carolina",
    "North Dakota",
    "Ohio",
    "Oklahoma",
    "Oregon",
    "Pennsylvania",
    "Puerto Rico",
    "Rhode Island",
    "South Carolina",
    "South Dakota",
    "Tennessee",
    "Texas",
    "Utah",
    "Vermont",
    "Virginia",
    "Washington",
    "West Virginia",
    "Wisconsin",
    "Wyoming",
)

# Two-letter codes that are rarely anything but a state when they sit in
# front of a five-digit number.
US_STATE_CODES = (
    "AK AR AZ CA DC FL GA IA IL KS KY LA MN MO MT NC ND NE NH NJ NM NV NY PR RI "
    "SC SD TN TX UT VA VT WA WI WV WY"
).split()

# Codes that double as common uppercase tokens (ID, IN, OR, ME, OK, HI, OH,
# CO, DE, PA, MA, MD, MI, MS, CT, AL). These only count as a state when a
# comma precedes them, as in "Boise, ID 83702", so "Patient ID 12345" is not
# read as a ZIP code.
US_STATE_CODES_AMBIGUOUS = "AL CO CT DE HI ID IN MA MD ME MI MS OH OK OR PA".split()
