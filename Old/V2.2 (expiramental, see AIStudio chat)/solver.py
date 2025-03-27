# --- START OF FILE solver.py ---

import streamlit as st
import re
import string
from collections import Counter, defaultdict
from typing import List, Tuple, Set
import random

# --- WordleSolver Class (No changes from previous version needed) ---
class WordleSolver:
    def __init__(self, wordlist_path: str, answers_path: str = None):
        self.wordlist_path = wordlist_path; self.answers_path = answers_path
        self.all_words = self.load_words(wordlist_path)
        if not self.all_words: self.likely_answers = set(); self.possible_answers = set(); return
        self.likely_answers = set()
        if answers_path:
            potential_answers = self.load_words(answers_path)
            if potential_answers:
                self.likely_answers = potential_answers.intersection(self.all_words)
                if not self.likely_answers: st.warning(f"'{answers_path}' common words check failed."); self.likely_answers = set()
            else: st.warning(f"Could not load '{answers_path}'."); self.likely_answers = set()
        else: st.info("No answers file provided."); self.likely_answers = self.all_words.copy()
        self.possible_answers = self.all_words.copy(); self.guesses_made = 0
        self.feedback_history = []; self._known_letters = ['' for _ in range(5)]
        self._misplaced_letters = [set() for _ in range(5)]; self._present_letters = set()
        self._excluded_letters = set(); self.switched_to_full_list = False

    def load_words(self, filepath: str) -> set[str]:
        try:
            try: f = open(filepath, 'r', encoding='utf-8'); words = {w.strip().lower() for w in f if len(w.strip())==5 and w.strip().isalpha()}
            except UnicodeDecodeError: f = open(filepath, 'r'); words = {w.strip().lower() for w in f if len(w.strip())==5 and w.strip().isalpha()}
            finally: f.close()
            if not words: st.warning(f"No valid words in '{filepath}'."); return set()
            return words
        except FileNotFoundError:
            if filepath == self.wordlist_path: st.error(f"Wordlist '{filepath}' not found."); st.stop()
            else: st.warning(f"Optional file '{filepath}' not found."); return set()
        except Exception as e: st.error(f"Error loading '{filepath}': {e}"); return set()

    def reset_solver_state(self):
        self._known_letters=['']*5; self._misplaced_letters=[set() for _ in range(5)]
        self._present_letters=set(); self._excluded_letters=set(); self.switched_to_full_list=False

    def _update_internal_state_from_history(self):
        self.reset_solver_state(); letter_counts_in_feedback = Counter()
        for guess, feedback in self.feedback_history:
            current_guess_letter_counts=Counter(guess); confirmed_non_gray_counts_in_guess=Counter()
            for i,(letter,status) in enumerate(zip(guess, feedback)): # Greens
                if status=='G': self._known_letters[i]=letter; self._present_letters.add(letter); confirmed_non_gray_counts_in_guess[letter]+=1; letter_counts_in_feedback[letter]=max(letter_counts_in_feedback[letter], confirmed_non_gray_counts_in_guess[letter])
            for i,(letter,status) in enumerate(zip(guess, feedback)): # Yellows/Grays
                if status=='Y': self._misplaced_letters[i].add(letter); self._present_letters.add(letter); confirmed_non_gray_counts_in_guess[letter]+=1; letter_counts_in_feedback[letter]=max(letter_counts_in_feedback[letter], confirmed_non_gray_counts_in_guess[letter])
                elif status=='X':
                    if letter not in self._present_letters and all(gl!=letter for gl in self._known_letters): self._excluded_letters.add(letter)

    def calculate_positional_frequencies(self, words: set[str]) -> list[Counter]:
        pf=[Counter() for _ in range(5)]; [pf[i].update(letter) for word in words for i,letter in enumerate(word)]; return pf
    def calculate_letter_frequencies(self, words: set[str]) -> Counter: return Counter("".join(words))

    def score_word(self, word: str, pf: list[Counter], lf: Counter, cpw: set[str], elim: bool = False) -> float:
        score=0.0; used=set(); is_cp=word in cpw; is_la=word in self.likely_answers
        for i,l in enumerate(word): # Penalties
            if l in self._excluded_letters and l not in self._present_letters and l not in self._known_letters: score-=1000
            if l in self._misplaced_letters[i]: score-=50
            if self._known_letters[i] and self._known_letters[i]!=l: score-=200
        for i,l in enumerate(word): # Scoring
            if l not in used: score+=pf[i].get(l,0); used.add(l)
            if elim and l in used: score+=lf.get(l,0)*0.6 # Add freq bonus once per letter in elim
        if is_la and is_cp and not elim: score*=1.8 # Bonuses
        elif is_cp and not elim: score*=1.1
        dpf=0.95 if is_la else 0.85;
        if len(set(word))<5: score*=dpf
        return max(score, -500)

    def filter_words(self) -> set[str]:
        self._update_internal_state_from_history(); filtered=self.all_words.copy()
        for i, l in enumerate(self._known_letters): # Greens
            if l: filtered={w for w in filtered if len(w)>i and w[i]==l}
        for l in self._present_letters: filtered={w for w in filtered if l in w} # Yellows (presence)
        for i, ms in enumerate(self._misplaced_letters): # Yellows (position)
            for l in ms: filtered={w for w in filtered if len(w)>i and w[i]!=l}
        ax={l for l in self._excluded_letters if l not in self._present_letters and all(gl!=l for gl in self._known_letters)} # Grays
        for l in ax: filtered={w for w in filtered if l not in w}
        min_lc=Counter(); exact_lc={} # Counts
        for g,f in self.feedback_history:
            gc=Counter(g); ngc=Counter(); grc=Counter()
            for i,(l,s) in enumerate(zip(g,f)):
                if s in ('G','Y'): ngc[l]+=1
                elif s=='X': grc[l]+=1
            for l,c in gc.items(): min_lc[l]=max(min_lc[l], ngc[l]);
            if grc[l]>0: exact_lc[l]=ngc[l]
        final=set() # Apply counts
        for w in filtered:
            wc=Counter(w); valid=True
            for l,mc in min_lc.items():
                if wc[l]<mc: valid=False; break
            if not valid: continue
            for l,ec in exact_lc.items():
                 if wc[l]!=ec: valid=False; break
            if valid: final.add(w)
        self.possible_answers=final; return self.possible_answers

    def suggest_guess(self) -> str:
        cp=self.filter_words();
        if not cp: return "No valid words remaining."
        pal=cp.intersection(self.likely_answers) # Possible And Likely
        pool=set(); phase_msg=""
        if not self.switched_to_full_list and pal: # Phase 1
            pool=pal; phase_msg="(From Likely List)"
        else: # Phase 2
            if not self.switched_to_full_list and self.likely_answers: self.switched_to_full_list=True; st.toast("Switching: Considering all valid words.")
            pool=cp; phase_msg="(From Full List)" if self.likely_answers else "(From Word List)"
            if not pool: return "Error: Pool empty after switch."
        elim=len(pool)>100 and st.session_state.guesses_made<3
        opf=self.calculate_positional_frequencies(cp); olf=self.calculate_letter_frequencies(cp)
        best_w=""; best_s=-float('inf'); pool_score=pool # Score only from determined pool
        for w in pool_score:
            if any(w==h[0] for h in self.feedback_history): continue
            s=self.score_word(w, opf, olf, cp, elim)
            if s>best_s: best_s=s; best_w=w
            elif s==best_s and w<best_w: best_w=w # Tie-break alphabetically
        if not best_w and pool: return sorted(list(pool))[0] # Fallback
        elif not best_w: return "Could not determine guess."
        # print(f"Suggest: {best_w} {phase_msg}") # Debug
        return best_w


# --- Streamlit App ---

# Constants (no changes needed)
MAX_GUESSES = 6; WORD_LENGTH = 5; CORRECT = "G"; PRESENT = "Y"; ABSENT = "X"
DEFAULT_FEEDBACK = [ABSENT] * WORD_LENGTH; FEEDBACK_OPTIONS = [ABSENT, PRESENT, CORRECT]
COLORS = {CORRECT: "#6aaa64", PRESENT: "#c9b458", ABSENT: "#787c7e", "empty": "#ffffff", "tbd": "#d3d6da"}

# Helper Functions (no changes needed)
@st.cache_resource
def get_solver(): # Loads solver instance
    wordlist_file="wordlist.txt"; answers_file="answers.txt" # Or None
    _solver = WordleSolver(wordlist_file, answers_file)
    if not _solver.all_words: st.error("Failed to load wordlist."); st.stop()
    return _solver
def get_color(s, fb=False): return COLORS.get("tbd",COLORS["empty"]) if fb and s==ABSENT else COLORS.get(s,COLORS["empty"])
def display_guess_grid(h): # Restored CSS
    st.markdown("""<style>.tile{display:inline-flex;justify-content:center;align-items:center;width:55px;height:55px;border:2px solid #d3d6da;margin:3px;font-size:2.2em;font-weight:bold;text-transform:uppercase;color:white;vertical-align:middle;line-height:55px;}.tile[data-state="G"]{background-color:#6aaa64;border-color:#6aaa64;}.tile[data-state="Y"]{background-color:#c9b458;border-color:#c9b458;}.tile[data-state="X"]{background-color:#787c7e;border-color:#787c7e;}.tile[data-state="empty"]{background-color:#ffffff;border-color:#d3d6da;box-shadow:none;}.tile[data-state="tbd"]{background-color:#ffffff;border-color:#878a8c;color:black !important;}</style>""", unsafe_allow_html=True)
    for gw, fl in h: # Past guesses
        cols = st.columns(WORD_LENGTH); [cols[i].markdown(f'<div class="tile" data-state="{fl[i] if i<len(fl) else "empty"}">{gw[i].upper() if i<len(gw) else " "}</div>', unsafe_allow_html=True) for i in range(WORD_LENGTH)]
    for _ in range(MAX_GUESSES - len(h)): # Empty rows
        cols = st.columns(WORD_LENGTH); [cols[i].markdown('<div class="tile" data-state="empty"> </div>', unsafe_allow_html=True) for i in range(WORD_LENGTH)]

# --- App Initialization & State (no changes needed) ---
st.set_page_config(page_title="Wordle Solver+", layout="wide"); st.title("🧠 Wordle Solver+")
st.caption("Enter guess, click squares for feedback (Gray->Yellow->Green), Submit.")
solver = get_solver()
if 'guesses_made' not in st.session_state: # Simplified init check
    st.session_state.clear(); st.session_state.guesses_made = 0 # Full reset if key missing
    st.session_state.solver_history = []; st.session_state.display_history = []
    st.session_state.current_feedback = list(DEFAULT_FEEDBACK)
    st.session_state.game_over = False; st.session_state.solved = False
    st.session_state.last_suggested = ""; st.session_state.current_guess_input = ""

# --- New Game Button (no changes needed) ---
if st.sidebar.button("🔄 New Game"):
    st.session_state.clear(); st.session_state.guesses_made = 0 # Reset state completely
    solver.feedback_history = []; solver.possible_answers = solver.all_words.copy()
    solver.reset_solver_state(); st.rerun()

# --- Main Game Area ---
grid_col, control_col = st.columns([2, 1])
with grid_col: st.subheader("Guess Grid"); display_guess_grid(st.session_state.display_history)
with control_col:
    st.subheader("Controls")
    if st.session_state.game_over: # Game Over Display
        if st.session_state.solved: st.success(f"Solved in {st.session_state.guesses_made} guesses! 🎉")
        else: st.error(f"Failed in {st.session_state.guesses_made} guesses.")
        fp=solver.possible_answers;
        if len(fp)==1: st.info(f"Answer likely: **{list(fp)[0].upper()}**")
        elif 1<len(fp)<=20: st.info(f"Possible: {', '.join(sorted(w.upper() for w in fp))}")
        elif len(fp)>20: st.info(f"{len(fp)} possibilities remain.")
        else: st.warning("No words match feedback."); st.write("Start 'New Game'.")
    else: # Active Game Controls
        # --- *** REVISED Word Count Display Logic *** ---
        display_count = 0
        count_label = "Possible Words Remaining" # Default label
        current_possible = solver.possible_answers # Get current state after potential filtering

        if st.session_state.guesses_made == 0 and solver.likely_answers:
            # Before first guess: Show initial count of likely answers
            display_count = len(solver.likely_answers)
            count_label = "Likely Starting Words"
        elif not solver.switched_to_full_list and solver.likely_answers:
            # After first guess, BUT before switching: Show count of POSSIBLE AND LIKELY words
            possible_and_likely = current_possible.intersection(solver.likely_answers)
            display_count = len(possible_and_likely)
            count_label = "Likely Words Remaining"
        else:
            # After switching (or if no likely_answers ever existed): Show count of ALL possible words
            display_count = len(current_possible)
            count_label = "Possible Words Remaining"

        st.metric(count_label, display_count) # Display the calculated count and label
        # --- End of Revised Count Logic ---

        # --- Solver Suggestion (no changes needed) ---
        suggested_guess = solver.suggest_guess(); st.session_state.last_suggested = suggested_guess
        suffix = ""
        if solver.switched_to_full_list: suffix = " (From Full List)" if solver.likely_answers else " (From Word List)"
        elif suggested_guess in solver.likely_answers: suffix = " (From Likely List)"
        elif suggested_guess in solver.possible_answers : suffix = " (Possible)"
        st.info(f"Solver Suggests: **{suggested_guess.upper()}**{suffix}")

        # --- User Guess Input (no changes needed) ---
        guess = st.text_input("Enter Your Guess:", placeholder=suggested_guess.upper(), max_chars=WORD_LENGTH, key="user_input", value=st.session_state.get("current_guess_input","")).lower().strip(); st.session_state.current_guess_input=guess

        # --- Feedback Input (no changes needed) ---
        st.write("Set feedback for your guess:")
        if len(guess)==WORD_LENGTH and guess.isalpha():
            cols=st.columns(WORD_LENGTH); fb_list=st.session_state.current_feedback
            for i, l in enumerate(guess):
                with cols[i]:
                    stat=fb_list[i]; tc=get_color(stat); bc=tc if stat!=ABSENT else "#878a8c"; txc="white" if stat!=ABSENT else "black"
                    if st.button(f"##{l.upper()}_{i}", key=f"fb{i}", help="Cycle: Gray->Yellow->Green"):
                        idx=FEEDBACK_OPTIONS.index(stat); nidx=(idx+1)%len(FEEDBACK_OPTIONS); st.session_state.current_feedback[i]=FEEDBACK_OPTIONS[nidx]; st.rerun()
                    st.markdown(f'<div style="display:flex;justify-content:center;align-items:center;width:45px;height:45px;background-color:{tc};border:2px solid {bc};border-radius:3px;margin:2px auto;font-size:1.8em;font-weight:bold;text-transform:uppercase;color:{txc};cursor:pointer;user-select:none;">{l.upper()}</div>', unsafe_allow_html=True)

            # --- Submit Button (no changes needed) ---
            st.write("---")
            if st.button("✅ Submit Guess and Feedback", use_container_width=True):
                if len(guess)!=WORD_LENGTH or not guess.isalpha(): st.warning("Enter valid 5-letter word.")
                elif guess not in solver.all_words: st.warning(f"'{guess.upper()}' not in word list.")
                else:
                    fb_str="".join(st.session_state.current_feedback)
                    solver.feedback_history.append((guess, fb_str))
                    st.session_state.display_history.append((guess, list(st.session_state.current_feedback)))
                    st.session_state.guesses_made+=1
                    if fb_str==CORRECT*WORD_LENGTH: st.session_state.solved=True; st.session_state.game_over=True
                    elif st.session_state.guesses_made>=MAX_GUESSES: st.session_state.game_over=True
                    st.session_state.current_feedback=list(DEFAULT_FEEDBACK); st.session_state.current_guess_input=""
                    st.rerun()
        elif guess: st.warning("Type 5-letter word.")
        else: st.caption("Type guess above.")

# Optional: Display remaining words (no changes needed)
show_final = (not st.session_state.game_over and solver.possible_answers and 0<len(solver.possible_answers)<=20) or \
             (st.session_state.game_over and solver.possible_answers and 1<len(solver.possible_answers)<=20)
if show_final:
    with grid_col:
        st.write("---"); lbl="Final Potential" if st.session_state.game_over else "Top Potential"; st.write(f"**{lbl} Answers ({len(solver.possible_answers)}):**")
        likely=[w for w in solver.possible_answers if w in solver.likely_answers]; other=[w for w in solver.possible_answers if w not in solver.likely_answers]
        st.info(", ".join(w.upper() for w in (sorted(likely)+sorted(other))[:20]))

# --- END OF FILE solver.py ---
