/*
 * Calibration du potentiometre de pedale
 * ======================================
 *
 * A televerser AVANT pedale.ino. Ce croquis n'envoie rien d'utile au PC :
 * il affiche la valeur BRUTE du potentiometre pour que tu releves ta course
 * reelle, puis tu reportes les deux nombres dans pedale.ino.
 *
 * MODE D'EMPLOI
 *   1. Televerse ce croquis
 *   2. Outils > Moniteur serie, vitesse 115200 bauds
 *   3. Pedale au REPOS -> note la valeur affichee
 *   4. Pedale ENFONCEE A FOND -> note la valeur affichee
 *   5. Appuie et relache lentement plusieurs fois : les colonnes mini et
 *      maxi retiennent les extremes rencontres
 *   6. Reporte ces deux nombres dans pedale.ino (SEUIL_BAS et SEUIL_HAUT)
 *
 * ENVOIE 'r' dans le moniteur serie pour remettre les extremes a zero.
 *
 * CABLAGE
 *   potentiometre lineaire 10 kOhm (type B10K, PAS un logarithmique A10K)
 *     une extremite -> 5V
 *     curseur       -> A0
 *     autre extremite -> GND
 *
 *   Si la valeur DIMINUE quand tu appuies, permute simplement les deux
 *   fils des extremites. Le curseur reste sur A0.
 */

const uint8_t BROCHE = A0;
const unsigned long PERIODE_MS = 200;

int mini = 1023;
int maxi = 0;
unsigned long dernier = 0;

void setup() {
  Serial.begin(115200);
  Serial.println();
  Serial.println(F("=== Calibration de la pedale ==="));
  Serial.println(F("Appuie et relache lentement. 'r' remet a zero."));
  Serial.println();
  Serial.println(F(" brut   mini   maxi   course   position"));
}

void loop() {
  if (Serial.available() && Serial.read() == 'r') {
    mini = 1023; maxi = 0;
    Serial.println(F("-- extremes remis a zero --"));
  }

  if (millis() - dernier < PERIODE_MS) return;
  dernier = millis();

  int brut = analogRead(BROCHE);
  if (brut < mini) mini = brut;
  if (brut > maxi) maxi = brut;
  int course = maxi - mini;

  char ligne[48];
  snprintf(ligne, sizeof(ligne), "%5d  %5d  %5d  %6d   ",
           brut, mini, maxi, course);
  Serial.print(ligne);

  // Barre visuelle : 40 caracteres sur la course reellement observee.
  // Elle rend le reglage mecanique bien plus facile a juger que des chiffres.
  int longueur = 0;
  if (course > 10) {
    longueur = (long)(brut - mini) * 40 / course;
  }
  for (int i = 0; i < 40; i++) Serial.print(i < longueur ? '#' : '.');
  Serial.println();
}
