#include "recognizer.h"
void parse_pssm(Recognizer *rec, double* matrix, int len){
  rec->matrix = matrix;
  rec->alt_f = NULL;
  rec->edges = NULL;
  rec->null_f = NULL;
  rec->bin_s = 0;
  rec->len = len;
  rec->feat = 'p';
}

void parse_shape(Recognizer* rec, double* null_f, double* alt_f, double* edges, int bin_s, int len, char feat) {
  rec->matrix = NULL;
  rec->null_f = null_f;
  rec->alt_f = alt_f;
  rec->edges = edges;
  rec->bin_s = bin_s;
  rec->len = len;
  rec->feat = feat;
}

void print_rec(Recognizer *rec){
  printf("Recognizer Feature: %c\n", rec->feat);
  printf("Recognizer Length %i\n", rec->len);
  if (rec->feat != 'p'){
    print_shape(rec);
  }else{
    print_pssm(rec);
  }
}

void print_pssm(Recognizer *rec){
  for (int j = 0; j < 4; j++){
    printf(" ");
    for (int k = 0; k < rec->len; k++){
      printf("%5.2f ", rec->matrix[k * 4 + j]);
    }
    printf("\n");
  }
}

void print_shape(Recognizer *rec){
  
  printf("Null frequencies:\n");
  for (int j = 0; j < rec->bin_s - 1; j++){
    printf(" [%5.2f, %5.2f]: %8.5f\n", rec->edges[j], rec->edges[j+1], rec->null_f[j]);
  }


  printf("Alt frequencies:\n");
  for (int j = 0; j < rec->bin_s - 1; j++){
    printf(" [%5.2f, %5.2f]: %8.5f\n", rec->edges[j], rec->edges[j+1], rec->alt_f[j]);
  }
  
}

void pssm_row( Recognizer* rec,  const char* seq,  int len, double* row){
  double score = 0.0;
  double* matrix = rec->matrix;
  for (int i = 0; i < len; i++) {
    score = 0.0;
    for (int j = 0; j < rec->len; j++) {
      switch(seq[i + j]) {
        case 'a':
        case 'A':
          score += matrix[j * 4 + 0];
          break;
        
        case 'g':
        case 'G':
          score += matrix[j * 4 + 1];
          break;
        
        case 'c':
        case 'C':
          score += matrix[j * 4 + 2];
          break;
        
        case 't':
        case 'T':
          score += matrix[j * 4 + 3];
          break;
      }
    }
    row[i] = score;
  }

}

void mgw_row( Recognizer* rec,  const char* seq,  int len, double* row){
  int n_pent = rec->len - 4;
  int n_bins = rec->bin_s;
  double alt_f = 0.0;
  double null_f = 0.0;
  double* alt = rec->alt_f;
  double* null = rec->null_f;
  double* edges = rec->edges;
  double* pent_s = (double*)malloc(n_pent * sizeof(double));
  double score = 0.0;
  int idx = 0;
  for (int i = 0; i < len; i++){
    for (int j = i; j < i + n_pent; j++){
      score = 0.0;
      idx = 0;
      for (int k = j; k < j + 5; k++){
        switch(seq[k]){
          case 'a':
          case 'A':
            idx += pow(4, 4 - (k - j)) * 0;
            break;

          case 'g':
          case 'G':
            idx += pow(4, 4 - (k - j)) * 1;
            break;

          case 'c':
          case 'C':
            idx += pow(4, 4 - (k - j)) * 2;
            break;

          case 't':
          case 'T':
            idx += pow(4, 4 - (k - j)) * 3;
            break;
        }
      }
      pent_s[j - i] = MGW_SCORES[idx];
    }
    score = shape_average_mgw_prot(pent_s, n_pent);
    alt_f = get_bin_frequency(score, alt, edges, n_bins);
    null_f = get_bin_frequency(score, null, edges, n_bins);
    score = log2f(alt_f / null_f);
    double t_score = score;
    if (score < BIG_NEGATIVE)
      score = BIG_NEGATIVE;

    if (score > BIG_POSITIVE){
      score = BIG_POSITIVE;
      print_rec(rec);
      exit(1);
    }
    row[i] = score;
  }
  free(pent_s);
}

void prot_row( Recognizer* rec,  const char* seq,  int len, double* row){
  int n_pent = rec->len - 4;
  int n_bins = rec->bin_s;
  double alt_f = 0.0;
  double null_f = 0.0;
  double* alt = rec->alt_f;
  double* null = rec->null_f;
  double* edges = rec->edges;
  double* pent_s = (double*)malloc(n_pent * sizeof(double));
  double score = 0.0;
  int idx = 0;
  char** seqs = (char**)malloc(n_pent * sizeof(char*));
  for (int i = 0; i < n_pent; i++){
    seqs[i] = (char*)malloc(6 * sizeof(char));
    seqs[i][5] = '\0';
  }

  for (int i = 0; i < len; i++){
    for (int j = i; j < i + n_pent; j++){
      score = 0.0;
      idx = 0;
      for (int k = j; k < j + 5; k++){
        seqs[j - i][k - j] = seq[k];
        switch(seq[k]){
          case 'a':
          case 'A':
            idx += pow(4, 4 - (k - j)) * 0;
            break;

          case 'g':
          case 'G':
            idx += pow(4, 4 - (k - j)) * 1;
            break;

          case 'c':
          case 'C':
            idx += pow(4, 4 - (k - j)) * 2;
            break;

          case 't':
          case 'T':
            idx += pow(4, 4 - (k - j)) * 3;
            break;
        }
      }
      pent_s[j - i] = PROT_SCORES[idx];

    }
    score = shape_average_mgw_prot(pent_s, n_pent);
    double t_score = score;
    alt_f = get_bin_frequency(score, alt, edges, n_bins);
    null_f = get_bin_frequency(score, null, edges, n_bins);
    score = log2f(alt_f / null_f);
    if (score < BIG_NEGATIVE)
      score = BIG_NEGATIVE;

    if (score > BIG_POSITIVE){
      printf("null_f = %f\n", null_f);
      printf("alt_f = %f\n", alt_f);
      printf("t_score: %f\n", t_score);
      printf("sequences pentamers\n");
      for (int i = 0; i < n_pent; i++){
        printf("%s, %6.3f\n", seqs[i], pent_s[i]);
      }
      print_rec(rec);
      score = BIG_POSITIVE;
      exit(1);
    } 
    row[i] = score;
  }
  free(pent_s);

}

void roll_row( Recognizer* rec,  const char* seq,  int len, double* row){
  int n_pent = rec->len - 4;
  int n_bins = rec->bin_s;
  double alt_f = 0.0;
  double null_f = 0.0;
  double* alt = rec->alt_f;
  double* null = rec->null_f;
  double* edges = rec->edges;
  double* pent_s = (double*)malloc((n_pent * 2) * sizeof(double));
  double score = 0.0;
  int idx = 0;

  for (int i = 0; i < len; i++){
    for (int j = i; j < (i + n_pent); j++){
      score = 0.0;
      idx = 0;
      for (int k = j; k < (j + 5); k++){
        switch(seq[k]){
          case 'a':
          case 'A':
            idx += pow(4, 4 - (k - j)) * 0;
            break;

          case 'g':
          case 'G':
            idx += pow(4, 4 - (k - j)) * 1;
            break;

          case 'c':
          case 'C':
            idx += pow(4, 4 - (k - j)) * 2;
            break;

          case 't':
          case 'T':
            idx += pow(4, 4 - (k - j)) * 3;
            break;
        }
      }
      pent_s[j - i] = ROLL_SCORES[idx];
      pent_s[j - i + n_pent] = ROLL_SCORES[idx + 1024];
    }
    score = shape_average(pent_s, n_pent * 2);
    alt_f = get_bin_frequency(score, alt, edges, n_bins);
    null_f = get_bin_frequency(score, null, edges, n_bins);
    score = log2f(alt_f / null_f);
    if (score < BIG_NEGATIVE)
      score = BIG_NEGATIVE;

    if (score > BIG_POSITIVE)
      score = BIG_POSITIVE;

    row[i] = score;
  }
  free(pent_s);

}

void helt_row( Recognizer* rec,  const char* seq,  int len, double* row){
  int n_pent = rec->len - 4;
  int n_bins = rec->bin_s;
  double alt_f = 0.0;
  double null_f = 0.0;
  double* alt = rec->alt_f;
  double* null = rec->null_f;
  double* edges = rec->edges;
  double* pent_s = (double*)malloc((n_pent * 2) * sizeof(double));
  double score = 0.0;
  int idx = 0;

  char** seqs = (char**)malloc(n_pent * sizeof(char*));
  for (int i = 0; i < n_pent; i++){
    seqs[i] = (char*)malloc(6 * sizeof(char));
    seqs[i][5] = '\0';
  }

  for (int i = 0; i < len; i++){
    for (int j = i; j < i + n_pent; j++){
      score = 0.0;
      idx = 0;
      for (int k = j; k < j + 5; k++){
        seqs[j - i][k - j] = seq[k];
        switch(seq[k]){
          case 'a':
          case 'A':
            idx += pow(4, 4 - (k - j)) * 0;
            break;

          case 'g':
          case 'G':
            idx += pow(4, 4 - (k - j)) * 1;
            break;

          case 'c':
          case 'C':
            idx += pow(4, 4 - (k - j)) * 2;
            break;

          case 't':
          case 'T':
            idx += pow(4, 4 - (k - j)) * 3;
            break;
        }
      }
      pent_s[j - i] = HELT_SCORES[idx];
      pent_s[j - i + n_pent] = HELT_SCORES[idx + 1024];
    }
    score = shape_average(pent_s, n_pent * 2);
    double t_score = score;
    alt_f = get_bin_frequency(score, alt, edges, n_bins);
    null_f = get_bin_frequency(score, null, edges, n_bins);
    score = log2f(alt_f / null_f);
    if (score < BIG_NEGATIVE)
      score = BIG_NEGATIVE;

    if (score > BIG_POSITIVE){

      printf("null_f = %f\n", null_f);
      printf("alt_f = %f\n", alt_f);
      printf("t_score: %f\n", t_score);
      printf("sequences pentamers\n");
      for (int i = 0; i < n_pent; i++){
        printf("%s: %6.3f, %6.3f\n", seqs[i], pent_s[i], pent_s[i + n_pent]);
      }
      print_rec(rec);
      score = BIG_POSITIVE;
      exit(1);
    }

    row[i] = score;
  }
  free(pent_s);

}

void shape_row( Recognizer* rec,  const char* seq,  int len, double* row){
  switch(rec->feat) {
    case 'm':
    case 'M':
      mgw_row(rec, seq, len, row);
      break;

    case 't':
    case 'T':
      prot_row(rec, seq, len, row);
      break;

    case 'r':
    case 'R':
      roll_row(rec, seq, len, row);
      break;

    case 'h':
    case 'H':
      helt_row(rec, seq, len, row);
      break;
  }

}

void score_row( Recognizer* rec,  const char* seq,  int len, double* row){
  if (rec->feat == 'p' || rec->feat == 'P'){
    pssm_row(rec, seq, len, row);
  }else{
    shape_row(rec, seq, len, row);
  }
}