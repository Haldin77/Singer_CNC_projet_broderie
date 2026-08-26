/*
 * Pedale de la brodeuse Singer -- croquis Arduino Uno
 * ===================================================
 *
 * Lit un potentiometre solidaire de la pedale d'origine et envoie sa
 * position au PC par le port serie USB.
 *
 * CABLAGE
 *   potentiometre 10 kOhm lineaire
 *     extremite 1 -> 5V
 *     curseur     -> A0
 *     extremite 3 -> GND
 *
 *   Le 5 V ne pose aucun probleme ici : l'ADC de l'Uno est prevu pour.
 *   C'est sur l'ESP32 qu'il serait destructeur.
 *
 * PROTOCOLE
 *   Une ligne par mesure, envoyee seulement quand la valeur CHANGE :
 *     P0     pedale relachee
 *     P1..P100  pourcentage d'enfoncement
 *   Plus une ligne "PING" toutes les secondes, meme a l'arret.
 *
 *   Le PING est le coeur de la securite : c'est lui qui prouve que la
 *   pedale est toujours la. Si le PC cesse de le recevoir -- cable
 *   debranche, Uno plante --, il arrete la machine. Sans ce battement,
 *   une pedale muette serait indistinguable d'une pedale au repos.
 *
 * ATTENTION
 *   La pedale Singer d'origine commute du 230 V. Elle doit etre
 *   TOTALEMENT deconnectee du secteur. Seul le potentiometre, mecaniquement
 *   solidaire de sa course, est relie a l'Uno.
 */

const uint8_t BROCHE_PEDALE = A0;

// Zone morte en debut de course. Un potentiometre ne revient jamais
// exactement a zero, et une pedale au repos ne doit RIEN faire.
const int SEUIL_BAS = 450;      // sur 1023

// Marge en fin de course : on atteint 100 % avant la butee mecanique,
// pour ne pas dependre du dernier millimetre.
const int SEUIL_HAUT = 1010;

// Filtre passe-bas ASYMETRIQUE. Le cable de la pedale passe pres des
// drivers, qui rayonnent : sans lissage, la consigne tremblerait.
// Mais le relachement est un ordre d'arret : il doit passer vite.
//   montee  : douce, filtre le bruit
//   descente : franche, l'arret est detecte en un ou deux cycles
const float LISSAGE_MONTEE = 0.25;
const float LISSAGE_DESCENTE = 0.65;

// Hysteresis : on n'emet que si la valeur bouge d'au moins ce pourcentage.
// Evite d'inonder le port serie pour du bruit.
const int PAS_MINIMAL = 2;

const unsigned long PERIODE_PING_MS = 1000;
const unsigned long PERIODE_LECTURE_MS = 20;

float valeur_lissee = 0.0;
int dernier_envoye = -1;
unsigned long dernier_ping = 0;
unsigned long derniere_lecture = 0;

void setup() {
  Serial.begin(115200);
  // Premiere lecture sans lissage, pour ne pas partir de zero si la
  // pedale est deja enfoncee au branchement.
  valeur_lissee = analogRead(BROCHE_PEDALE);
  Serial.println(F("PEDALE v1"));
}

int versPourcentage(float brut) {
  if (brut <= SEUIL_BAS) return 0;
  if (brut >= SEUIL_HAUT) return 100;
  return (int)((brut - SEUIL_BAS) * 100.0 / (SEUIL_HAUT - SEUIL_BAS));
}

void loop() {
  unsigned long maintenant = millis();

  if (maintenant - derniere_lecture >= PERIODE_LECTURE_MS) {
    derniere_lecture = maintenant;

    int brut = analogRead(BROCHE_PEDALE);
    float lissage = (brut < valeur_lissee) ? LISSAGE_DESCENTE : LISSAGE_MONTEE;
    valeur_lissee += (brut - valeur_lissee) * lissage;
    int pourcent = versPourcentage(valeur_lissee);

    // Le retour a zero est TOUJOURS transmis, sans hysteresis : c'est un
    // ordre d'arret, il ne doit jamais etre retenu par un filtre.
    bool changement = (pourcent == 0 && dernier_envoye != 0)
                   || (abs(pourcent - dernier_envoye) >= PAS_MINIMAL);

    if (changement) {
      Serial.print('P');
      Serial.println(pourcent);
      dernier_envoye = pourcent;
      dernier_ping = maintenant;
    }
  }

  if (maintenant - dernier_ping >= PERIODE_PING_MS) {
    dernier_ping = maintenant;
    Serial.println(F("PING"));
  }
}
