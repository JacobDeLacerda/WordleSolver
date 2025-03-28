# --- START OF FILE solver.py ---

import streamlit as st
import re
import string
from collections import Counter, defaultdict
from typing import List, Tuple, Set
import heapq # Needed for efficient top-N selection

# --- Paste or Import the WordleSolver Class ---
# (Mostly identical, with changes in suggest_guess)
class WordleSolver:
    def __init__(self, wordlist_path: str, answers_path: str = None):
        self.all_words = self.load_words(wordlist_path)
        # Use answers_path if provided, otherwise use all_words
        if answers_path:
            try:
                potential_answers = self.load_words(answers_path)
                # Ensure answers are also in the main word list
                self.possible_answers = potential_answers.intersection(self.all_words)
                if not self.possible_answers and self.all_words: # Check if all_words loaded ok
                    st.warning("Answers file resulted in empty set after intersection with wordlist. Using full wordlist for answers.")
                    self.possible_answers = self.all_words.copy()
                elif not self.possible_answers and not self.all_words:
                     # If all_words is also empty, something is fundamentally wrong
                     st.error("Failed to load both wordlist and answers. Cannot initialize possible answers.")
                     self.possible_answers = set() # Keep it empty
                elif not potential_answers and self.all_words:
                    # If answers failed to load but wordlist is okay
                     st.warning(f"Could not load '{answers_path}' or it was empty. Using full wordlist for potential answers.")
                     self.possible_answers = self.all_words.copy()

            except Exception as e: # Catch potential errors during intersection/loading
                 st.error(f"Error processing answers file '{answers_path}': {e}. Falling back to full wordlist.")
                 self.possible_answers = self.all_words.copy()

        else:
            self.possible_answers = self.all_words.copy()

        self.guesses_made = 0
        self.feedback_history = []  # Store (guess, feedback) tuples
        # --- State tracking specific to filtering logic ---
        self._known_letters = ['' for _ in range(5)]  # Green letters ('G')
        self._misplaced_letters = [set() for _ in range(5)] # Yellow letters ('Y'), per position they *cannot* be
        self._present_letters = set() # All yellow letters found anywhere
        self._excluded_letters = set() # Gray letters ('X')

    def load_words(self, filepath: str) -> set[str]:
        """Loads words from a file, ensuring they are valid."""
        words = set()
        try:
            with open(filepath, 'r', encoding='utf-8') as f: # Added encoding
                words = {word.strip().lower() for word in f if len(word.strip()) == 5 and word.strip().isalpha()}
            if not words:
                # Use st.warning for non-critical file issues unless it's the main wordlist
                st.warning(f"Warning: No valid 5-letter words found in '{filepath}'.")
            return words
        except FileNotFoundError:
            st.error(f"Error: File not found at '{filepath}'. Cannot load words.")
            return set()
        except Exception as e:
            st.error(f"An error occurred loading '{filepath}': {e}")
            return set()

    def reset_solver_state(self):
        """Resets the internal state derived from feedback."""
        self._known_letters = ['' for _ in range(5)]
        self._misplaced_letters = [set() for _ in range(5)]
        self._present_letters = set()
        self._excluded_letters = set()

    def _update_internal_state_from_history(self):
        """Rebuilds internal G/Y/X tracking from feedback_history."""
        self.reset_solver_state()
        letter_counts_in_feedback = Counter() # Tracks max known counts for letters

        for guess, feedback in self.feedback_history:
            current_guess_letter_counts = Counter(guess)
            confirmed_non_gray_counts = Counter() # Non-gray instances in *this* guess

            # Process Greens first to establish known positions and minimum counts
            for i, (letter, status) in enumerate(zip(guess, feedback)):
                 if status == 'G':
                    # If a different letter was previously known for this position, something is wrong with input.
                    # However, Wordle feedback rules prevent this scenario if input is correct.
                    # We'll overwrite here, assuming latest feedback is correct.
                    self._known_letters[i] = letter
                    self._present_letters.add(letter) # Green implies present
                    confirmed_non_gray_counts[letter] += 1

            # Process Yellows and Grays
            for i, (letter, status) in enumerate(zip(guess, feedback)):
                if status == 'Y':
                    # Yellow means present but not in this position
                    self._misplaced_letters[i].add(letter)
                    self._present_letters.add(letter)
                    confirmed_non_gray_counts[letter] += 1
                    # Ensure this yellow isn't contradicting a known green
                    if self._known_letters[i] == letter:
                        # This state indicates contradictory feedback (e.g., marking green then yellow for same slot)
                        # This *shouldn't* happen with valid Wordle rules/input, but log if it does.
                        # Consider adding a warning if such inconsistencies are detected.
                        pass # Or st.warning(...)
                elif status == 'X':
                    # Gray means the letter is NOT present *more times* than confirmed non-gray occurrences
                    # If a letter is marked Gray, and it's also marked Green/Yellow in the same guess,
                    # it should NOT be added to the global excluded set.
                    if letter not in self._present_letters and letter not in self._known_letters:
                         # Add to excluded set ONLY if it's not known to be Green anywhere or Present (Yellow) anywhere
                         self._excluded_letters.add(letter)


    def calculate_positional_frequencies(self, words: set[str]) -> list[Counter]:
        """Calculates letter frequencies for each position."""
        positional_frequencies = [Counter() for _ in range(5)]
        for word in words:
            for i, letter in enumerate(word):
                positional_frequencies[i][letter] += 1
        return positional_frequencies

    def calculate_letter_frequencies(self, words: set[str]) -> Counter:
        """Calculates overall letter frequencies."""
        return Counter("".join(words))

    def score_word(self, word: str, positional_frequencies: list[Counter], letter_frequencies: Counter, possible_answers: set[str], elimination_mode: bool = False) -> float:
        """Scores a word based on frequencies and elimination potential."""
        score = 0.0
        used_letters = set()

        is_possible_answer = word in possible_answers

        # --- Pre-computation of penalties/bonuses based on state ---
        # These checks don't depend on the word's letters yet
        penalty_for_duplicates = 0.9 if len(set(word)) < 5 else 1.0
        possible_answer_bonus = 1.2 if is_possible_answer and not elimination_mode else 1.0

        for i, letter in enumerate(word):
            letter_score = 0.0 # Score for this specific letter position

            # --- Strong Penalties ---
            # 1. Letter known to be excluded entirely
            if letter in self._excluded_letters:
                # Only apply penalty if it's truly excluded (not overridden by a known G/Y)
                 active_exclusions = self._excluded_letters - self._present_letters - set(filter(None, self._known_letters))
                 if letter in active_exclusions:
                     return -float('inf') # Instant disqualification - never suggest words with truly excluded letters

            # 2. Letter known to be Green but used in the wrong spot
            # This check is partially redundant with filtering, but adds explicit penalty if filter fails?
            # No, filtering should handle this. If a word violates known greens, it won't be in possible_answers
            # and if scoring all_words, this check is valid.
            if self._known_letters[i] and self._known_letters[i] != letter:
                 # This word violates a known green letter, massive penalty or filter it out earlier
                 return -float('inf') # Disqualify if scoring from all_words; should be filtered otherwise

            # 3. Letter known to be Yellow/Misplaced *in this specific position*
            if letter in self._misplaced_letters[i]:
                 score -= 50 # Moderate penalty (can still be useful sometimes, e.g., eliminating positions)


            # --- Scoring based on frequencies (only if letter not penalized above) ---
            if letter not in used_letters:
                # Score based on positional frequency within remaining possible answers
                letter_score += positional_frequencies[i].get(letter, 0) # Use .get for safety

                # Elimination bonus (especially in elimination_mode or early game)
                if elimination_mode:
                    # Use overall frequency in possible answers as proxy for info gain
                    letter_score += letter_frequencies.get(letter, 0) * 0.5

            score += letter_score
            used_letters.add(letter) # Track unique letters used in this word

        # Apply overall word bonuses/penalties
        score *= possible_answer_bonus
        score *= penalty_for_duplicates

        # Minor penalty for suggesting already known green letters again (less info gain)
        green_reuse_penalty = 0.95 ** sum(1 for i, letter in enumerate(word) if self._known_letters[i] == letter)
        score *= green_reuse_penalty

        return score


    def filter_words(self) -> set[str]:
        """Filters the possible words based on accumulated feedback."""
        # Make sure the internal state (G/Y/X lists) is up-to-date from history
        self._update_internal_state_from_history()
        filtered = self.possible_answers.copy()

        # --- Apply filters based on G, Y, X states ---

        # 1. Green letters must match
        for i, known_letter in enumerate(self._known_letters):
            if known_letter:
                filtered = {word for word in filtered if len(word) == 5 and word[i] == known_letter} # Added len check for safety

        # 2. Yellow letters must be present BUT NOT in the excluded position
        for letter in self._present_letters:
            # Ensure the letter is present somewhere
            filtered = {word for word in filtered if letter in word}
        for i, misplaced_set in enumerate(self._misplaced_letters):
            for letter in misplaced_set:
                 # Ensure the letter is NOT in this specific position i
                filtered = {word for word in filtered if len(word) == 5 and word[i] != letter} # Added len check

        # 3. Gray letters must NOT be present (unless accounted for by G/Y)
        # Determine which letters are truly excluded
        active_exclusions = self._excluded_letters - self._present_letters - set(filter(None, self._known_letters))
        for letter in active_exclusions:
             filtered = {word for word in filtered if letter not in word}

        # 4. Handle duplicate letter counts implied by feedback (Advanced)
        min_letter_counts = Counter() # Minimum required count for each letter
        exact_letter_counts = {}      # Letters known to have an exact count

        for guess, feedback in self.feedback_history:
             guess_counts = Counter(guess)
             non_gray_counts = Counter() # Count G/Y occurrences of each letter in this guess

             for i, (letter, status) in enumerate(zip(guess, feedback)):
                 if status in ('G', 'Y'):
                     non_gray_counts[letter] += 1

             for letter, count in guess_counts.items():
                 # Update minimum required count based on observed G/Y
                 min_letter_counts[letter] = max(min_letter_counts[letter], non_gray_counts[letter])

                 # Check if a Gray implies an exact count
                 gray_present_in_feedback = any(fb == 'X' and g == letter for g, fb in zip(guess, feedback))

                 if gray_present_in_feedback and non_gray_counts[letter] == min_letter_counts[letter]:
                    # If we saw a gray 'L' in 'LEVEL' (feedback like YXXGX) and we only saw one Y/G 'L',
                    # then the answer must have *exactly* one 'L'.
                    # Check if we already have a potentially conflicting exact count
                    if letter in exact_letter_counts and exact_letter_counts[letter] != non_gray_counts[letter]:
                         # This indicates conflicting feedback across different guesses, which shouldn't happen in Wordle.
                         # Might indicate user input error. Handle gracefully - maybe warn?
                         # For now, let's overwrite with the latest deduction, though ideally, this state is impossible.
                         pass # Or st.warning(f"Contradictory count info for '{letter}'")
                    exact_letter_counts[letter] = non_gray_counts[letter]


        # Apply count filtering
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
                 if word_counts[letter] != exact_count:
                     valid = False
                     break
            if valid:
                final_filtered.add(word)

        # Update the solver's possible answers list
        self.possible_answers = final_filtered
        return self.possible_answers


    def suggest_guess(self, elimination_mode: bool = False, num_suggestions: int = 5) -> List[str]:
        """
        Suggests the best guess(es) based on scoring.
        Returns a list of the top 'num_suggestions' words, sorted by score.
        """
        current_possible = self.filter_words() # Ensure filtering happens first based on history

        if not current_possible:
            return ["No valid words remaining."]
        if len(current_possible) == 1:
            # If only one possibility, that's the only suggestion
            return [list(current_possible)[0]]

        positional_frequencies = self.calculate_positional_frequencies(current_possible)
        letter_frequencies = self.calculate_letter_frequencies(current_possible)

        # Use a min-heap to efficiently keep track of the top N scores.
        # Store (score, is_possible, word) tuples. We use is_possible for tie-breaking.
        # Python's heapq is a min-heap, so we store negative scores to keep the *highest* scores.
        top_suggestions_heap = []

        # Decide which set of words to score: all words for elimination, or just possible answers
        word_pool = self.all_words if elimination_mode else current_possible
        word_pool = word_pool - {hist[0] for hist in self.feedback_history} # Exclude already guessed words

        # Optimization: Limit pool size if it's extremely large in elimination mode
        # if elimination_mode and len(word_pool) > 5000:
        #    # Consider sampling or smarter selection if performance is an issue
        #    pass


        for word in word_pool:
            # Score the word
            score = self.score_word(word, positional_frequencies, letter_frequencies, current_possible, elimination_mode)

            if score == -float('inf'): # Skip disqualified words immediately
                continue

            is_possible = word in current_possible
            # Use a tuple for sorting: (-score, not is_possible, word)
            # -score: Higher scores come first (min-heap on negative score).
            # not is_possible: False (0) comes before True (1), so possible answers are prioritized in ties.
            # word: Alphabetical tie-breaking as the last resort.
            heap_item = (-score, not is_possible, word)

            if len(top_suggestions_heap) < num_suggestions:
                heapq.heappush(top_suggestions_heap, heap_item)
            else:
                # Push the new item and pop the smallest (largest negative score) if the new one is better
                heapq.heappushpop(top_suggestions_heap, heap_item)

        # Extract the words from the heap and sort them correctly
        # The heap contains (-score, not_possible, word). We want to sort by score DESC, then is_possible ASC, then word ASC.
        sorted_suggestions = sorted(top_suggestions_heap, key=lambda x: (x[0], x[1], x[2])) # Sorts by -score (so highest score first), then not_possible (so possible first), then word

        # Return just the words
        final_suggestions = [word for neg_score, not_possible, word in sorted_suggestions]

        if not final_suggestions:
             # Fallback if somehow no words scored > -inf
             if current_possible:
                 return sorted(list(current_possible))[:num_suggestions] # Return first few possible answers alphabetically
             else:
                 return ["Could not determine best guess."]

        return final_suggestions


# --- Streamlit App ---

# Constants
MAX_GUESSES = 6
WORD_LENGTH = 5
CORRECT = "G"
PRESENT = "Y"
ABSENT = "X"
DEFAULT_FEEDBACK = [ABSENT] * WORD_LENGTH
FEEDBACK_OPTIONS = [ABSENT, PRESENT, CORRECT]
COLORS = {CORRECT: "#6aaa64", PRESENT: "#c9b458", ABSENT: "#787c7e", "empty": "#d3d6da"}
NUM_SUGGESTIONS_TO_GET = 5 # How many suggestions to fetch from the solver

# Helper Functions
@st.cache_resource # Cache the solver instance loading
def get_solver():
    # --- IMPORTANT: Adjust file paths if needed ---
    # Use relative paths assuming files are in the same directory as the script
    wordlist_file = "wordlist.txt"
    answers_file = "answers.txt" # Make this None if you don't have a separate answers file
    # --------------------------------------------
    solver = WordleSolver(wordlist_file, answers_file)
    if not solver.all_words: # Check if loading the main wordlist failed
        st.error("CRITICAL: Failed to load the main wordlist. The application cannot continue.")
        st.stop() # Stop execution if main wordlist isn't loaded
    # Initial filtering based on empty history (just to populate possible_answers count)
    solver.filter_words()
    return solver

def get_color(status):
    return COLORS.get(status, COLORS["empty"])

def display_guess_grid(history):
    st.markdown("""
        <style>
            .tile {
                display: inline-flex;
                justify-content: center;
                align-items: center;
                width: 50px;
                height: 50px;
                border: 2px solid #d3d6da;
                margin: 2px;
                font-size: 2em;
                font-weight: bold;
                text-transform: uppercase;
                color: white; /* Letter color */
            }
            .tile[data-state="G"] { background-color: #6aaa64; border-color: #6aaa64; }
            .tile[data-state="Y"] { background-color: #c9b458; border-color: #c9b458; }
            .tile[data-state="X"] { background-color: #787c7e; border-color: #787c7e; }
            .tile[data-state="empty"] { background-color: white; border-color: #d3d6da; }
            .tile[data-state="tbd"] { background-color: white; border-color: #878a8c; color: black !important; } /* Style for current guess input */
        </style>
    """, unsafe_allow_html=True)

    # Display past guesses
    for guess_word, feedback_list in history:
        cols = st.columns(WORD_LENGTH)
        for i, letter in enumerate(guess_word):
            state = feedback_list[i]
            with cols[i]:
                st.markdown(f'<div class="tile" data-state="{state}">{letter}</div>', unsafe_allow_html=True)

    # Display empty rows for remaining guesses
    remaining_guesses = MAX_GUESSES - len(history)
    for _ in range(remaining_guesses):
        cols = st.columns(WORD_LENGTH)
        for i in range(WORD_LENGTH):
            with cols[i]:
                st.markdown(f'<div class="tile" data-state="empty"> </div>', unsafe_allow_html=True)


# --- App Initialization & State ---
st.set_page_config(page_title="Streamlit Wordle Solver", layout="wide")
st.title("🧠 Streamlit Wordle Solver")
st.caption("Enter your guess, click the buttons below to set Wordle's feedback (Gray/Yellow/Green), then Submit.")

solver = get_solver()

# Initialize session state variables if they don't exist
if 'solver_history' not in st.session_state:
    st.session_state.solver_history = [] # List of (guess, feedback_str) tuples for the solver
    st.session_state.display_history = [] # List of (guess, feedback_list) for display grid
    st.session_state.guesses_made = 0
    st.session_state.current_feedback = list(DEFAULT_FEEDBACK) # Feedback for the *next* guess
    st.session_state.game_over = False
    st.session_state.solved = False
    st.session_state.current_guess_input = ""
    st.session_state.top_suggestions = [] # Holds the list of suggested words
    st.session_state.suggestion_index = 0 # Index of the currently shown suggestion


# --- Reset Logic for "New Game" Button ---
def reset_game():
    st.session_state.solver_history = []
    st.session_state.display_history = []
    st.session_state.guesses_made = 0
    st.session_state.current_feedback = list(DEFAULT_FEEDBACK)
    st.session_state.game_over = False
    st.session_state.solved = False
    st.session_state.current_guess_input = ""
    st.session_state.top_suggestions = []
    st.session_state.suggestion_index = 0

    # --- Reset Solver Instance State ---
    solver.feedback_history = []
    solver.guesses_made = 0

    # Reload words to reset possible_answers correctly based on initial files
    wordlist_file = "wordlist.txt" # Define paths again or get from config
    answers_file = "answers.txt"
    solver.all_words = solver.load_words(wordlist_file) # Reload main list

    if not solver.all_words:
         st.error("CRITICAL: Failed to reload wordlist on New Game. Cannot continue.")
         st.stop()

    if answers_file:
        try:
            potential_answers = solver.load_words(answers_file)
            solver.possible_answers = potential_answers.intersection(solver.all_words)
            if not solver.possible_answers and solver.all_words:
                st.warning("Answers file reloaded but empty intersection. Using full wordlist.")
                solver.possible_answers = solver.all_words.copy()
            elif not potential_answers and solver.all_words:
                 st.warning(f"Could not reload '{answers_file}'. Using full wordlist.")
                 solver.possible_answers = solver.all_words.copy()
            # If both failed, possible_answers remains empty, handled elsewhere
        except Exception as e:
             st.error(f"Error reloading answers file: {e}. Using full wordlist.")
             solver.possible_answers = solver.all_words.copy()
    else:
        solver.possible_answers = solver.all_words.copy() # Fallback to all words

    # Initial filter needed to update counts, etc.
    solver.filter_words()
    st.rerun()

if st.sidebar.button("New Game"):
    reset_game()


# --- Main Game Area ---
grid_col, control_col = st.columns([2, 1])

with grid_col:
    st.subheader("Guess Grid")
    display_guess_grid(st.session_state.display_history)

with control_col:
    st.subheader("Controls")

    if st.session_state.game_over:
        if st.session_state.solved:
            st.success(f"Solved in {st.session_state.guesses_made} guesses! 🎉")
        else:
            st.error("Game Over! Failed to solve within 6 guesses.")

        # Try to show the potential answer if only one remains
        remaining_answers = solver.possible_answers
        if len(remaining_answers) == 1:
            st.info(f"The word was likely: **{list(remaining_answers)[0].upper()}**")
        elif 1 < len(remaining_answers) <= 10:
             st.info(f"Possible remaining words: {', '.join(sorted(list(remaining_answers)))}")
        else:
            st.info("Could not determine the exact word.")

        st.write("Start a 'New Game' from the sidebar.")

    else: # Game is ongoing
        # --- Solver Suggestion ---
        remaining_count = len(solver.possible_answers)
        st.write(f"Possible words remaining: **{remaining_count}**")

        # Get suggestions if not already calculated for this turn
        if not st.session_state.top_suggestions:
            elimination_mode = st.session_state.guesses_made < 2 and remaining_count > 10 # Adjusted heuristic
            st.session_state.top_suggestions = solver.suggest_guess(
                elimination_mode=elimination_mode,
                num_suggestions=NUM_SUGGESTIONS_TO_GET
            )
            st.session_state.suggestion_index = 0 # Reset index when getting new suggestions

            # Automatically set the input field to the top suggestion
            if st.session_state.top_suggestions:
                st.session_state.current_guess_input = st.session_state.top_suggestions[0]
            else:
                st.session_state.current_guess_input = "" # Should ideally not happen


        # Display Current Suggestion and Next Suggestion Button
        if st.session_state.top_suggestions:
            current_suggestion_index = st.session_state.suggestion_index
            current_suggestion = st.session_state.top_suggestions[current_suggestion_index]
            total_suggestions = len(st.session_state.top_suggestions)

            # Determine if the current suggestion is just for elimination
            is_elimination_only = current_suggestion not in solver.possible_answers and remaining_count > 1

            st.info(f"Solver Suggests ({current_suggestion_index + 1}/{total_suggestions}): **{current_suggestion.upper()}** {'(Elimination Guess)' if is_elimination_only else ''}")

            # --- "Suggest Different Word" Button ---
            if total_suggestions > 1:
                cols_sugg = st.columns([3,1]) # Make button smaller
                with cols_sugg[1]: # Place button to the right
                    if st.button("Next Suggestion", key="next_sugg_btn", disabled=(current_suggestion_index >= total_suggestions - 1)):
                        st.session_state.suggestion_index += 1
                        # Update the text input field to the new suggestion
                        st.session_state.current_guess_input = st.session_state.top_suggestions[st.session_state.suggestion_index]
                        st.rerun() # Rerun to update the displayed suggestion and input field

        else:
            st.warning("Solver could not provide a suggestion.")

        # --- User Guess Input ---
        # Use text_input, ensuring its value is controlled by session state
        guess = st.text_input(
            "Enter Your Guess:",
            value=st.session_state.current_guess_input,
            max_chars=WORD_LENGTH,
            key="user_guess_input_area", # Use a consistent key
            on_change=lambda: setattr(st.session_state, 'current_guess_input', st.session_state.user_guess_input_area) # Update state on change
        ).lower().strip()


        # --- Feedback Input ---
        st.write("Click to set feedback for your guess:")
        if len(guess) == WORD_LENGTH and guess.isalpha():
            feedback_cols = st.columns(WORD_LENGTH)
            current_feedback_list = st.session_state.current_feedback

            for i, letter in enumerate(guess):
                with feedback_cols[i]:
                    current_status = current_feedback_list[i]
                    button_label = f"{letter.upper()}" # Show letter on button

                    # Cycle through feedback options on click
                    if st.button(button_label, key=f"fb_{i}", help=f"Click to cycle feedback for '{letter.upper()}' (Current: {current_status})"):
                        current_index = FEEDBACK_OPTIONS.index(current_status)
                        next_index = (current_index + 1) % len(FEEDBACK_OPTIONS)
                        st.session_state.current_feedback[i] = FEEDBACK_OPTIONS[next_index]
                        st.rerun() # Rerun to update the button color below

                    # Display colored square below button to show current selection
                    color = get_color(current_status)
                    st.markdown(f'<div style="width:30px; height:10px; background-color:{color}; margin: auto; border: 1px solid black;"></div>', unsafe_allow_html=True)


            # --- Submit Button ---
            if st.button("Submit Guess and Feedback"):
                # Validation
                if len(guess) != WORD_LENGTH or not guess.isalpha():
                    st.warning("Please enter a valid 5-letter word.")
                elif guess not in solver.all_words:
                    # Check if it's allowed by the game (some Wordle variants allow non-list words)
                    # For now, enforce strict list check
                    st.warning(f"'{guess.upper()}' is not in the valid word list.")
                else:
                    # Process the guess
                    feedback_str = "".join(st.session_state.current_feedback)

                    # Update Solver State (using its internal history tracker)
                    solver.feedback_history.append((guess, feedback_str))
                    solver.guesses_made += 1 # Increment solver's internal count

                    # Update Streamlit State for display and game logic
                    st.session_state.solver_history.append((guess, feedback_str)) # Keep separate history if needed, but maybe redundant
                    st.session_state.display_history.append((guess, list(st.session_state.current_feedback))) # Store list for display
                    st.session_state.guesses_made += 1

                    # Check for win/loss
                    if feedback_str == CORRECT * WORD_LENGTH:
                        st.session_state.solved = True
                        st.session_state.game_over = True
                    elif st.session_state.guesses_made >= MAX_GUESSES:
                        st.session_state.game_over = True

                    # --- Reset for next turn ---
                    st.session_state.current_feedback = list(DEFAULT_FEEDBACK)
                    st.session_state.current_guess_input = "" # Clear input field
                    st.session_state.top_suggestions = [] # Clear old suggestions to force recalculation
                    st.session_state.suggestion_index = 0

                    # Trigger filter and rerun
                    # solver.filter_words() # filter_words is called at the start of suggest_guess now
                    st.rerun() # Rerun the app to reflect changes and get new suggestion
        elif guess: # If guess is partially typed or invalid
            st.warning("Type a 5-letter word to enable feedback input.")

# Optional: Display remaining words if few are left
if not st.session_state.game_over and len(solver.possible_answers) <= 15 and len(solver.possible_answers) > 1 :
    with grid_col: # Put this below the grid
        st.write("---")
        st.write(f"**Potential Answers ({len(solver.possible_answers)}):**")
        st.write(", ".join(sorted(list(solver.possible_answers))))

# --- END OF FILE solver.py ---
