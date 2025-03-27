# --- START OF FILE solver.py ---

import streamlit as st
import re
import string
from collections import Counter, defaultdict
from typing import List, Tuple, Set
import random # Added for potential sampling, though commented out for now

# --- Paste or Import the WordleSolver Class ---
class WordleSolver:
    def __init__(self, wordlist_path: str, answers_path: str = None):
        # 1. Load ALL valid words first
        self.all_words = self.load_words(wordlist_path)
        if not self.all_words:
            # If all_words fails to load, we can't proceed. get_solver handles st.stop().
            self.likely_answers = set()
            self.possible_answers = set()
            return

        # 2. Load the likely answers (curated list)
        self.likely_answers = set()
        if answers_path:
            potential_answers = self.load_words(answers_path)
            if potential_answers:
                # Store the intersection as the set of likely answers
                self.likely_answers = potential_answers.intersection(self.all_words)
                if not self.likely_answers:
                    st.warning(f"'{answers_path}' loaded, but had no words in common with '{wordlist_path}'. Prioritization disabled.")
            else:
                 st.warning(f"Could not load or parse '{answers_path}'. Prioritization disabled.")
        else:
            st.info("No separate answers file provided. Solver will not prioritize common words.")
            # Treat all words as equally likely initially if no answers file
            self.likely_answers = self.all_words.copy()

        # 3. Initialize possible_answers with ALL valid words
        # This is the set that will be filtered down.
        self.possible_answers = self.all_words.copy()

        # --- Rest of the state remains the same ---
        self.guesses_made = 0
        self.feedback_history = []
        self._known_letters = ['' for _ in range(5)]
        self._misplaced_letters = [set() for _ in range(5)]
        self._present_letters = set()
        self._excluded_letters = set()

    # --- load_words remains the same ---
    def load_words(self, filepath: str) -> set[str]:
        """Loads words from a file, ensuring they are valid."""
        try:
            # Try UTF-8 first, then fallback for wider compatibility
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    words = {word.strip().lower() for word in f if len(word.strip()) == 5 and word.strip().isalpha()}
            except UnicodeDecodeError:
                 st.warning(f"UTF-8 decoding failed for '{filepath}', trying default encoding.")
                 with open(filepath, 'r') as f:
                    words = {word.strip().lower() for word in f if len(word.strip()) == 5 and word.strip().isalpha()}

            if not words:
                # Make this a warning, not error, as answers.txt might be optional/empty
                st.warning(f"Warning: No valid 5-letter words found in '{filepath}'.")
                return set()
            return words
        except FileNotFoundError:
            # Only error if the main wordlist is missing
            if filepath == getattr(self, 'wordlist_path', filepath): # Check if it's the main list path if attr exists
                 st.error(f"Error: Main wordlist file not found at '{filepath}'. Cannot continue.")
            else:
                 st.warning(f"Optional file not found at '{filepath}'.")
            return set()
        except Exception as e:
            st.error(f"An error occurred loading '{filepath}': {e}")
            return set()

    # --- reset_solver_state remains the same ---
    def reset_solver_state(self):
        """Resets the internal state derived from feedback."""
        self._known_letters = ['' for _ in range(5)]
        self._misplaced_letters = [set() for _ in range(5)]
        self._present_letters = set()
        self._excluded_letters = set()

    # --- _update_internal_state_from_history remains the same ---
    def _update_internal_state_from_history(self):
        """Rebuilds internal G/Y/X tracking from feedback_history."""
        self.reset_solver_state()
        letter_counts_in_feedback = Counter() # Keep track of G/Y counts per letter across all guesses

        for guess, feedback in self.feedback_history:
            current_guess_letter_counts = Counter(guess)
            confirmed_non_gray_counts_in_guess = Counter() # Track non-gray instances *within this guess*

            # First pass for Greens
            for i, (letter, status) in enumerate(zip(guess, feedback)):
                if status == 'G':
                    self._known_letters[i] = letter
                    self._present_letters.add(letter)
                    confirmed_non_gray_counts_in_guess[letter] += 1
                    letter_counts_in_feedback[letter] = max(letter_counts_in_feedback[letter], confirmed_non_gray_counts_in_guess[letter])


            # Second pass for Yellows and Grays
            for i, (letter, status) in enumerate(zip(guess, feedback)):
                if status == 'Y':
                    self._misplaced_letters[i].add(letter)
                    self._present_letters.add(letter)
                    confirmed_non_gray_counts_in_guess[letter] += 1
                    letter_counts_in_feedback[letter] = max(letter_counts_in_feedback[letter], confirmed_non_gray_counts_in_guess[letter])

                elif status == 'X':
                     # Only add to excluded if it's definitively not present anywhere (i.e., not Green/Yellow)
                     # and we haven't seen enough G/Y instances of it already in this or previous guesses
                     # to account for all its occurrences in *this* specific guess.
                    if letter not in self._present_letters and letter not in self._known_letters:
                         # Check against the count within *this* guess if needed
                        if confirmed_non_gray_counts_in_guess[letter] < current_guess_letter_counts[letter]:
                             self._excluded_letters.add(letter)
                    # Refined check: If a letter is marked gray, but we previously saw it green/yellow,
                    # only exclude it if the number of gray instances EXCEEDS the number of times it appeared
                    # in the guess MINUS the number of confirmed G/Y instances across all guesses.
                    # This handles cases like 'SASSY' guess -> 'XGXYX' feedback for 'SPIKY' answer more robustly.
                    # We know 'S' isn't in pos 0, 2, 4. But we know one 'S' is present (pos 1).
                    # The logic needs to ensure 'S' isn't *fully* excluded.
                    # Let's simplify: A letter is excluded *only if* it has received 'X' feedback AND
                    # it has *never* received 'G' or 'Y' feedback across the entire history for *any* instance.
                    # The min/max count filtering handles the quantities later.
                    if letter not in self._present_letters and all(l != letter for l in self._known_letters):
                         self._excluded_letters.add(letter)


    # --- calculate_positional_frequencies remains the same ---
    def calculate_positional_frequencies(self, words: set[str]) -> list[Counter]:
        """Calculates letter frequencies for each position."""
        positional_frequencies = [Counter() for _ in range(5)]
        if not words: return positional_frequencies # Handle empty set
        for word in words:
            for i, letter in enumerate(word):
                positional_frequencies[i][letter] += 1
        return positional_frequencies

    # --- calculate_letter_frequencies remains the same ---
    def calculate_letter_frequencies(self, words: set[str]) -> Counter:
        """Calculates overall letter frequencies."""
        if not words: return Counter() # Handle empty set
        return Counter("".join(words))

    # --- MODIFIED score_word ---
    def score_word(self, word: str, positional_frequencies: list[Counter], letter_frequencies: Counter, current_possible_words: set[str], elimination_mode: bool = False) -> float:
        """Scores a word based on frequencies and elimination potential. NOW prioritizes likely answers."""
        score = 0.0
        used_letters = set()

        # Check if the word being scored is among the *currently possible* words
        is_currently_possible = word in current_possible_words
        # Check if the word being scored is in the original *likely answers* list
        is_likely_answer = word in self.likely_answers

        # --- Penalties first ---
        for i, letter in enumerate(word):
            # Heavily penalize guessing letters known to be excluded entirely
            if letter in self._excluded_letters:
                 # Check if this exclusion is correct given known G/Y status (redundant with filter? maybe)
                 if letter not in self._present_letters and letter not in self._known_letters:
                    score -= 1000
                    # If a letter is excluded, its contribution should be negative, don't 'continue'

            # Penalize guessing letters known to be misplaced in this specific position
            if letter in self._misplaced_letters[i]:
                 score -= 50

            # Penalize using known-wrong letters in green slots
            if self._known_letters[i] and self._known_letters[i] != letter:
                 score -= 200 # Penalize harder if contradicting a green


        # --- Scoring based on letter value ---
        for i, letter in enumerate(word):
            if letter not in used_letters: # Score each unique letter only once for freq bonus
                # Core scoring based on positional frequency in remaining *possible* words
                score += positional_frequencies[i].get(letter, 0)

                # Elimination bonus: Add score based on overall frequency
                if elimination_mode:
                    # Give higher bonus for letters frequent in the remaining set
                    score += letter_frequencies.get(letter, 0) * 0.6 # Slightly increased weight

                used_letters.add(letter)

        # --- Apply Bonuses ---

        # BIG Bonus for being a "likely answer" (from answers.txt) AND currently possible
        if is_likely_answer and is_currently_possible and not elimination_mode:
             # Only apply this bonus if we're not purely focused on elimination
             score *= 1.8 # Significant boost for likely candidates

        # Smaller bonus just for being *possible* (relevant when scoring words from all_words pool)
        elif is_currently_possible and not elimination_mode:
             score *= 1.1 # Slight boost for any valid remaining possibility

        # Penalize words with duplicate letters slightly, more so if not likely
        # This encourages exploring more unique letters unless duplicates are strongly indicated
        duplicate_penalty_factor = 0.95 if is_likely_answer else 0.85
        if len(set(word)) < 5:
             score *= duplicate_penalty_factor

        # Ensure score isn't negative unless heavily penalized
        return max(score, -500) # Allow some negativity from penalties but floor it


    # --- MODIFIED filter_words ---
    def filter_words(self) -> set[str]:
        """Filters the possible words (which starts as ALL words) based on accumulated feedback."""
        # 1. Update G/Y/X state from history
        self._update_internal_state_from_history()

        # 2. Start filtering from the current set of possibilities
        # (self.possible_answers is updated in-place)
        filtered = self.possible_answers.copy()

        # Apply known green letters
        for i, known_letter in enumerate(self._known_letters):
            if known_letter:
                filtered = {word for word in filtered if len(word) > i and word[i] == known_letter} # Added len check

        # Apply known present (yellow) letters and their misplaced positions
        for letter in self._present_letters:
             # Ensure the letter is present somewhere
             filtered = {word for word in filtered if letter in word}
        # Ensure letter is NOT in the specific yellow positions
        for i, misplaced_set in enumerate(self._misplaced_letters):
            for letter in misplaced_set:
                 # Word cannot have this letter at this position i
                 filtered = {word for word in filtered if len(word) > i and word[i] != letter} # Added len check


        # Apply fully excluded (gray) letters
        # active_exclusions = self._excluded_letters - self._present_letters - set(filter(None, self._known_letters))
        # Simplified Exclusion: Exclude if in _excluded_letters AND not green/yellow anywhere
        active_exclusions = {l for l in self._excluded_letters if l not in self._present_letters and all(gl != l for gl in self._known_letters)}
        for letter in active_exclusions:
             # Word cannot contain this letter at all
             filtered = {word for word in filtered if letter not in word}


        # Handle duplicate letter counts implied by feedback (Advanced)
        # This part is crucial for words like 'PILLS', 'STATS' etc.
        min_letter_counts = Counter() # Minimum number of times a letter MUST appear
        exact_letter_counts = {} # For letters where we know the EXACT count (e.g., 'X' feedback confirmed it)

        for guess, feedback in self.feedback_history:
             guess_counts = Counter(guess)
             non_gray_count_in_guess = Counter()
             gray_count_in_guess = Counter()

             for i, (letter, status) in enumerate(zip(guess, feedback)):
                 if status in ('G', 'Y'):
                     non_gray_count_in_guess[letter] += 1
                 elif status == 'X':
                     gray_count_in_guess[letter] += 1

             for letter, count_in_guess in guess_counts.items():
                 # Update minimum required count based on G/Y feedback for this letter
                 min_letter_counts[letter] = max(min_letter_counts[letter], non_gray_count_in_guess[letter])

                 # Determine exact counts: If a letter received gray feedback in this guess,
                 # it means the total count of this letter in the answer is *exactly* the
                 # number of times it appeared as Green or Yellow in *this* guess.
                 if gray_count_in_guess[letter] > 0:
                      # If we already know an exact count, it must match (or something's wrong)
                      if letter in exact_letter_counts and exact_letter_counts[letter] != non_gray_count_in_guess[letter]:
                           # This indicates contradictory feedback, though ideally shouldn't happen
                           # We might trust the *latest* feedback or take the minimum? Let's trust latest.
                           # st.warning(f"Contradictory exact count for '{letter}'. Updating.")
                           pass # Let the latest assignment below override
                      exact_letter_counts[letter] = non_gray_count_in_guess[letter]


        # Apply min/exact count filtering
        final_filtered = set()
        for word in filtered:
            word_counts = Counter(word)
            valid = True

            # Check minimum counts
            for letter, min_count in min_letter_counts.items():
                if word_counts[letter] < min_count:
                    valid = False
                    break
            if not valid: continue

            # Check exact counts
            for letter, exact_count in exact_letter_counts.items():
                 # If the letter has an exact count constraint, the word must match it
                 if word_counts[letter] != exact_count:
                     valid = False
                     break
            # Check letters that MUST NOT be present (simplified exclusion handled above)
            # Can add a redundant check here if needed:
            # for letter in active_exclusions:
            #     if letter in word_counts:
            #         valid = False
            #         break
            # if not valid: continue

            if valid:
                final_filtered.add(word)

        # Update the solver's primary list of possible answers
        self.possible_answers = final_filtered
        return self.possible_answers


    # --- MODIFIED suggest_guess ---
    def suggest_guess(self, elimination_mode: bool = False) -> str:
        """Suggests the best guess based on scoring, prioritizing likely words."""
        # 1. Filter possibilities based on latest feedback
        current_possible = self.filter_words() # This updates self.possible_answers

        # 2. Handle edge cases
        if not current_possible:
            return "No valid words remaining."
        # --- REMOVED premature success declaration ---
        # if len(current_possible) == 1:
        #     # Don't declare victory here, let scoring decide if it's the best guess
        #     # return list(current_possible)[0]
        #     pass # Fall through to scoring

        # 3. Calculate frequencies based on the *current* possible words
        positional_frequencies = self.calculate_positional_frequencies(current_possible)
        letter_frequencies = self.calculate_letter_frequencies(current_possible)

        best_word = ""
        best_score = -float('inf')

        # 4. Decide the pool of words to *score* for suggesting the *next* guess
        #    - Elimination mode: Score ALL valid words to maximize info gain.
        #    - Normal mode: Score only the *currently possible* words.
        #      (Scoring all words *could* find a better eliminator even in normal mode,
        #       but let's prioritize finding the answer now)
        word_pool_to_score = self.all_words if elimination_mode else current_possible

        # Optimization: If the pool is massive in elimination mode, consider sampling
        # if elimination_mode and len(word_pool_to_score) > 3000:
        #     sample_size = 2000 + len(current_possible) # Ensure current possibles are included
        #     non_possible_sample = random.sample(list(self.all_words - current_possible), k=min(2000, len(self.all_words - current_possible)))
        #     word_pool_to_score = current_possible.union(set(non_possible_sample))
        #     print(f"Scoring sampled pool of {len(word_pool_to_score)}") # Debug


        # 5. Score words in the chosen pool
        for word in word_pool_to_score:
            # Don't suggest words already guessed
            if any(word == hist[0] for hist in self.feedback_history):
                continue

            score = self.score_word(word, positional_frequencies, letter_frequencies, current_possible, elimination_mode)

            # 6. Tie-breaking and Selection:
            is_likely = word in self.likely_answers
            is_possible = word in current_possible # Check if it fits current filters

            # --- Refined Tie-breaking ---
            if score > best_score:
                 best_score = score
                 best_word = word
            elif score == best_score:
                 # Priority order for ties:
                 # 1. Is the new word possible AND likely, but the old best wasn't? -> Choose new
                 if is_possible and is_likely and not (best_word in current_possible and best_word in self.likely_answers):
                     best_word = word
                 # 2. Is the new word possible (even if not likely), but the old best wasn't possible? -> Choose new
                 elif is_possible and not (best_word in current_possible):
                     best_word = word
                 # 3. Are both equally possible/likely status? Use alphabetical for consistency.
                 elif (is_possible == (best_word in current_possible)) and (is_likely == (best_word in self.likely_answers)):
                      if word < best_word:
                          best_word = word
                 # Add more tie-breaking? (e.g. fewer duplicate letters?) - Keep it simple for now.


        # If after all scoring, no word was selected (highly unlikely), return *something*
        if not best_word and current_possible:
             # Fallback: return the alphabetically first possible word
             return sorted(list(current_possible))[0]
        elif not best_word:
             return "Could not determine guess."


        return best_word


# --- Streamlit App ---

# Constants
MAX_GUESSES = 6
WORD_LENGTH = 5
CORRECT = "G"
PRESENT = "Y"
ABSENT = "X"
DEFAULT_FEEDBACK = [ABSENT] * WORD_LENGTH
FEEDBACK_OPTIONS = [ABSENT, PRESENT, CORRECT]
# Added 'tbd' state color for feedback buttons before click
COLORS = {CORRECT: "#6aaa64", PRESENT: "#c9b458", ABSENT: "#787c7e", "empty": "#ffffff", "tbd": "#d3d6da"} # White for empty, light gray for TBD

# Helper Functions
@st.cache_resource # Cache the solver instance loading
def get_solver():
    # --- Ensure these paths are correct relative to where you run `streamlit run` ---
    wordlist_file = "wordlist.txt"
    answers_file = "answers.txt" # Make this None if you ONLY have wordlist.txt
    # --------------------------------------------

    # --- Instantiate with updated __init__ logic ---
    _solver = WordleSolver(wordlist_file, answers_file)
    # --- Add check here: If main wordlist failed, stop ---
    if not _solver.all_words:
        st.error("Failed to load the main wordlist. Please check the file and path.")
        st.stop() # Stop execution if core list isn't loaded
    return _solver

# Updated get_color to use TBD
def get_color(status, is_feedback_button=False):
    if is_feedback_button and status == ABSENT: # Default state for feedback button is TBD
        return COLORS.get("tbd", COLORS["empty"])
    return COLORS.get(status, COLORS["empty"])

# Modified display_guess_grid slightly for clarity
def display_guess_grid(history):
    st.markdown("""
        <style>
            .tile {
                display: inline-flex; justify-content: center; align-items: center;
                width: 55px; height: 55px; /* Slightly larger */
                border: 2px solid #d3d6da; margin: 3px;
                font-size: 2.2em; font-weight: bold; text-transform: uppercase; color: white;
                vertical-align: middle; line-height: 55px; /* Better vertical centering */
            }
            /* Color states */
            .tile[data-state="G"] { background-color: #6aaa64; border-color: #6aaa64; }
            .tile[data-state="Y"] { background-color: #c9b458; border-color: #c9b458; }
            .tile[data-state="X"] { background-color: #787c7e; border-color: #787c7e; }
            /* Empty state */
            .tile[data-state="empty"] { background-color: #ffffff; border-color: #d3d6da; box-shadow: none;}
            /* TBD state (for current input row, maybe not needed here) */
            .tile[data-state="tbd"] { background-color: #ffffff; border-color: #878a8c; color: black !important; }
        </style>
    """, unsafe_allow_html=True)

    # Display past guesses
    for guess_word, feedback_list in history:
        cols = st.columns(WORD_LENGTH)
        for i, letter in enumerate(guess_word):
            state = feedback_list[i] if i < len(feedback_list) else "empty"
            letter_display = letter if i < len(guess_word) else " "
            with cols[i]:
                st.markdown(f'<div class="tile" data-state="{state}">{letter_display}</div>', unsafe_allow_html=True)

    # Display empty rows for remaining guesses
    remaining_guesses = MAX_GUESSES - len(history)
    for _ in range(remaining_guesses):
        cols = st.columns(WORD_LENGTH)
        for i in range(WORD_LENGTH):
            with cols[i]:
                # Use non-breaking space for empty tiles
                st.markdown(f'<div class="tile" data-state="empty"> </div>', unsafe_allow_html=True)


# --- App Initialization & State ---
st.set_page_config(page_title="Wordle Solver+", layout="wide") # Added + to title
st.title("🧠 Wordle Solver+") # Added + to title
st.caption("Enter your guess, click the squares below to set Wordle's feedback (Gray -> Yellow -> Green), then Submit.")

solver = get_solver()

# Initialize session state variables if they don't exist
if 'solver_history' not in st.session_state:
    st.session_state.solver_history = []
    st.session_state.display_history = []
    st.session_state.guesses_made = 0
    st.session_state.current_feedback = list(DEFAULT_FEEDBACK)
    st.session_state.game_over = False
    st.session_state.solved = False
    st.session_state.last_suggested = ""
    st.session_state.current_guess_input = ""


# --- New Game Button ---
if st.sidebar.button("🔄 New Game"):
    # Clear Streamlit state
    st.session_state.solver_history = []
    st.session_state.display_history = []
    st.session_state.guesses_made = 0
    st.session_state.current_feedback = list(DEFAULT_FEEDBACK)
    st.session_state.game_over = False
    st.session_state.solved = False
    st.session_state.last_suggested = ""
    st.session_state.current_guess_input = ""

    # Reset solver's internal state tracking AND possibilities
    solver.feedback_history = []
    # --- Reset possible_answers back to ALL words ---
    solver.possible_answers = solver.all_words.copy()
    # --- No need to reload files here, __init__ did that ---
    # --- Reset internal G/Y/X tracking ---
    solver.reset_solver_state()

    st.rerun() # Rerun to reflect the reset state


# --- Main Game Area ---
grid_col, control_col = st.columns([2, 1]) # Adjusted ratio slightly

with grid_col:
    st.subheader("Guess Grid")
    display_guess_grid(st.session_state.display_history) # Pass display history

with control_col:
    st.subheader("Controls")

    if st.session_state.game_over:
        if st.session_state.solved:
            st.success(f"Solved in {st.session_state.guesses_made} guesses! 🎉")
        else:
            st.error("Game Over! Failed to solve within 6 guesses.")
        # Now check the *filtered* possible_answers list
        final_possibilities = solver.possible_answers
        if len(final_possibilities) == 1:
             st.info(f"The answer was likely: **{list(final_possibilities)[0].upper()}**")
        elif 1 < len(final_possibilities) <= 10:
             st.info(f"Possible remaining answers: {', '.join(sorted([w.upper() for w in final_possibilities]))}")
        elif len(final_possibilities) > 10:
             st.info(f"{len(final_possibilities)} possibilities remained. Could not determine the exact word.")
        else: # len is 0
             st.warning("No possible words match the feedback provided. Please check your input.")

        st.write("Start a 'New Game' from the sidebar.")

    else:
        # --- Solver Suggestion ---
        # Use the solver's current state of possible_answers
        remaining_count = len(solver.possible_answers)
        st.metric("Possible Words Remaining", remaining_count) # Use a metric display

        # Determine if elimination mode should be used
        # Heuristic: Early turns OR if many possibilities remain without good candidates
        elimination_needed = remaining_count > 100 and st.session_state.guesses_made < 4
        elimination_mode = (st.session_state.guesses_made < 2 and remaining_count > 2) or elimination_needed

        suggested_guess = solver.suggest_guess(elimination_mode=elimination_mode)
        st.session_state.last_suggested = suggested_guess

        # Indicate if suggestion is likely/elimination
        suggestion_suffix = ""
        if suggested_guess in solver.likely_answers and suggested_guess in solver.possible_answers:
             suggestion_suffix = " (Likely Answer)"
        elif suggested_guess in solver.possible_answers:
             suggestion_suffix = " (Possible Answer)"
        elif elimination_mode:
             suggestion_suffix = " (Elimination Guess)"

        st.info(f"Solver Suggests: **{suggested_guess.upper()}**{suggestion_suffix}")


        # --- User Guess Input ---
        # Use suggestion as placeholder if input is empty or hasn't been manually changed yet
        guess_placeholder = suggested_guess.upper()
        # Let user type freely, manage state via the input value itself
        guess = st.text_input(
            "Enter Your Guess:",
            placeholder=guess_placeholder,
            max_chars=WORD_LENGTH,
            key="user_guess_input_field", # Unique key
            value=st.session_state.get("current_guess_input", "") # Use state if exists
        ).lower().strip()
        st.session_state.current_guess_input = guess # Update state continuously


        # --- Feedback Input ---
        st.write("Set feedback for your guess:")
        if len(guess) == WORD_LENGTH and guess.isalpha():
            feedback_cols = st.columns(WORD_LENGTH)
            current_feedback_list = st.session_state.current_feedback

            for i, letter in enumerate(guess):
                with feedback_cols[i]:
                    current_status = current_feedback_list[i]
                    # Use the colored tile itself as the button (more intuitive)
                    tile_color = get_color(current_status)
                    border_color = tile_color if current_status != ABSENT else "#878a8c" # Gray border for default absent
                    text_color = "white" if current_status != ABSENT else "black"

                    button_html = f"""
                    <div style="
                        display: flex; justify-content: center; align-items: center;
                        width: 45px; height: 45px; background-color: {tile_color};
                        border: 2px solid {border_color}; border-radius: 3px; margin: 2px auto;
                        font-size: 1.8em; font-weight: bold; text-transform: uppercase; color: {text_color};
                        cursor: pointer; user-select: none; /* Make it feel clickable */
                    ">
                        {letter.upper()}
                    </div>
                    """
                    # The button click triggers the rerun
                    if st.button(f"##{letter.upper()}_{i}", key=f"fb_btn_{i}", help=f"Click to cycle: Gray -> Yellow -> Green"): # Invisible label using ##
                         current_index = FEEDBACK_OPTIONS.index(current_status)
                         next_index = (current_index + 1) % len(FEEDBACK_OPTIONS)
                         st.session_state.current_feedback[i] = FEEDBACK_OPTIONS[next_index]
                         st.rerun() # Rerun to update the button color

                    # Display the button using markdown
                    st.markdown(button_html, unsafe_allow_html=True)


            # --- Submit Button ---
            st.write("---") # Separator
            if st.button("✅ Submit Guess and Feedback", use_container_width=True):
                # Validation
                if len(guess) != WORD_LENGTH or not guess.isalpha():
                    st.warning("Please enter a valid 5-letter word.")
                elif guess not in solver.all_words:
                    st.warning(f"'{guess.upper()}' is not in the valid word list.")
                else:
                    # --- Process the guess ---
                    feedback_str = "".join(st.session_state.current_feedback)

                    # Update Solver State (only history needed now, filtering happens in suggest/display)
                    solver.feedback_history.append((guess, feedback_str))
                    # No need to update solver.guesses_made, Streamlit state handles turn count

                    # Update Streamlit State
                    # Keep separate solver_history if debugging needed, otherwise maybe just use display_history
                    # st.session_state.solver_history.append((guess, feedback_str))
                    st.session_state.display_history.append((guess, list(st.session_state.current_feedback)))
                    st.session_state.guesses_made += 1

                    # Check for win/loss
                    if feedback_str == CORRECT * WORD_LENGTH:
                        st.session_state.solved = True
                        st.session_state.game_over = True
                    elif st.session_state.guesses_made >= MAX_GUESSES:
                        st.session_state.game_over = True

                    # Reset for next guess input
                    st.session_state.current_feedback = list(DEFAULT_FEEDBACK)
                    st.session_state.current_guess_input = "" # Clear input field state

                    # No need to call solver.filter_words() here, it's called by suggest_guess
                    # Just rerun to update the UI for the next turn
                    st.rerun()

        elif guess: # If guess is partially typed or invalid format
            st.warning("Type a 5-letter word to enable feedback input.")
        else: # No guess typed yet
             st.caption("Type your guess in the box above.")


# Optional: Display remaining words if few are left (using grid_col)
# Check after potential game over, so it shows final possibilities too
if not st.session_state.game_over and solver.possible_answers and len(solver.possible_answers) <= 20 and len(solver.possible_answers) > 0 :
    with grid_col: # Put this below the grid
        st.write("---")
        st.write(f"**Top Potential Answers ({len(solver.possible_answers)} total):**")
        # Show likely answers first, then others, limit total display
        likely_remaining = sorted([w for w in solver.possible_answers if w in solver.likely_answers])
        other_remaining = sorted([w for w in solver.possible_answers if w not in solver.likely_answers])
        display_list = likely_remaining + other_remaining
        st.info(", ".join(display_list[:20])) # Show max 20

elif st.session_state.game_over and solver.possible_answers and len(solver.possible_answers) <= 20 and len(solver.possible_answers) > 1:
     # Also show potentials if game over but > 1 possibility remained
     with grid_col:
         st.write("---")
         st.write(f"**Final Potential Answers ({len(solver.possible_answers)}):**")
         likely_remaining = sorted([w for w in solver.possible_answers if w in solver.likely_answers])
         other_remaining = sorted([w for w in solver.possible_answers if w not in solver.likely_answers])
         display_list = likely_remaining + other_remaining
         st.info(", ".join(display_list[:20]))

# --- END OF FILE solver.py ---
